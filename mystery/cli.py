"""Command line interface.

Two audiences. The author (an LLM generating a case) uses `validate` and `seal`.
The narrator (an LLM running play) uses everything else and gets JSON back,
which it renders as prose. The human never needs to type these — but can.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sys

from .schema import Case, ASSIST_LEVELS
from .seal import SealedCase
from .engine import Engine, State
from . import casebook
from .validate import validate

CASES_ROOT = "cases"
SCRATCH_ROOT = "scratch"

# How many past states to keep per case. Two hundred is more turns than a case
# runs, so in practice a case keeps every state it has ever had.
HISTORY_LIMIT = 200

# The command this run was invoked with, copied into each state history entry
# so a case holding something nobody typed can be traced to what wrote it.
# `main` sets it from the argv it parsed, which is not always the process argv:
# the test suite calls `main(["deduce", ...])` in-process.
_INVOCATION: list[str] = []


def _emit(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def _open(case_dir: str) -> tuple[SealedCase, Engine]:
    sealed = SealedCase(case_dir)
    if not sealed.exists():
        print(f"no sealed case at {case_dir}", file=sys.stderr)
        raise SystemExit(2)
    case = Case.from_dict(sealed.open_case())
    state = State.load(sealed.state_path) if os.path.exists(sealed.state_path) else State()
    return sealed, Engine(case, state)


def _history_path(sealed: SealedCase) -> str:
    return os.path.join(sealed.dir, "state.history.jsonl")


def _save(sealed: SealedCase, engine: Engine) -> None:
    """Write the state, keeping the one it replaces in `state.history.jsonl`.

    Every command that writes state goes through here, so no write is final.
    Each history line records the argv that caused it alongside the state that
    existed beforehand: `undo` restores that state, and the argv answers "what
    wrote this" when a case turns up holding something nobody typed. A
    development session testing `deduce` against a played case is the case
    that motivated it — see the note in CLAUDE.md.

    This is a repair tool for whoever owns the repo, not a rewind for the
    player. `undo` is hidden from `--help` and absent from the play skill,
    because a player who can take a turn back can take back a spent hint or a
    failed accusation, and the grade stops meaning anything.
    """
    path = sealed.state_path
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            prior = json.load(fh)
        line = json.dumps({"cmd": _INVOCATION, "state": prior}, ensure_ascii=False)
        lines = []
        hist = _history_path(sealed)
        if os.path.exists(hist):
            with open(hist, "r", encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        lines = (lines + [line])[-HISTORY_LIMIT:]
        with open(hist, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    engine.state.save(path)


def _close(sealed: SealedCase, engine: Engine) -> None:
    engine.state.turns += 1
    engine.state.turns_since_progress += 1
    _save(sealed, engine)


def cmd_validate(args) -> int:
    case = Case.load(args.draft)
    rep = validate(case)
    print(rep.render())
    return 0 if rep.ok else 1


def cmd_seal(args) -> int:
    case = Case.load(args.draft)
    rep = validate(case)
    if not rep.ok and not args.force:
        print(rep.render())
        print("\nRefusing to seal an unfair case. Fix the errors, or --force if you know better.")
        return 1
    if rep.warnings:
        print(rep.render(), file=sys.stderr)

    slug = args.slug or case.meta.get("slug") or os.path.splitext(os.path.basename(args.draft))[0]
    case_dir = os.path.join(CASES_ROOT, slug)
    sealed = SealedCase(case_dir)
    if sealed.exists() and not args.force:
        print(f"{case_dir} already holds a sealed case; pass --force to replace it", file=sys.stderr)
        return 1

    sealed.seal(case.to_json())
    State(assist=args.assist).save(sealed.state_path)

    # The opening is public — it's what the player is told up front.
    with open(os.path.join(case_dir, "BRIEF.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# {case.meta.get('title', slug)}\n\n{case.opening}\n\n")
        fh.write("## Persons of interest\n\n")
        for ch in case.cast:
            fh.write(f"- **{ch.name}** — {ch.role}. {ch.public_desc}\n")

    print(f"Sealed → {sealed.sealed_path}")
    print(f"Assist level: {args.assist}")
    if args.delete_draft:
        os.remove(args.draft)
        print(f"Draft deleted: {args.draft}")
    else:
        print(f"\nThe draft at {args.draft} is PLAINTEXT and contains the solution.")
        print("Delete it before playing, or you have spoiled yourself by accident.")
    return 0


def cmd_look(args) -> int:
    sealed, engine = _open(args.case)
    _emit(engine.look())
    _close(sealed, engine)
    return 0


def cmd_go(args) -> int:
    sealed, engine = _open(args.case)
    _emit(engine.travel(args.location))
    _close(sealed, engine)
    return 0


def cmd_examine(args) -> int:
    sealed, engine = _open(args.case)
    _emit(engine.examine(args.thing))
    _close(sealed, engine)
    return 0


def cmd_search(args) -> int:
    sealed, engine = _open(args.case)
    _emit(engine.search())
    _close(sealed, engine)
    return 0


def cmd_ask(args) -> int:
    sealed, engine = _open(args.case)
    _emit(engine.ask(args.who, args.topic))
    _close(sealed, engine)
    return 0


def cmd_deduce(args) -> int:
    """Rule on a conclusion the player has stated.

    `--as-stated` is required and is the player's own sentence. It is what gets
    filed and read back to them, and passing the case's wording instead would
    make a matched statement look different from an unmatched one.
    """
    sealed, engine = _open(args.case)
    _emit(engine.deduce(args.conclusion or "", args.evidence or [], args.as_stated))
    _close(sealed, engine)
    return 0


def cmd_journal(args) -> int:
    _, engine = _open(args.case)
    _emit(engine.journal())
    return 0


def cmd_note(args) -> int:
    """Write, strike, or amend a line in the player's notebook — or read it back.

    Deliberately not a turn: thinking on paper costs the detective nothing, and
    charging for it would teach the player not to do it.

    `--strike` rules a line through and leaves it legible; `--unstrike` takes
    the rule back off. `--amend` strikes and writes the replacement underneath;
    `--rewrite` fixes the wording in place. `--tear-out` is the last resort for
    a line that was never reasoning — a duplicate or a typo.
    """
    sealed, engine = _open(args.case)
    if args.amend is not None:
        if not args.text:
            _emit({"ok": False, "error": "--amend needs the replacement text"})
            return 2
        result = engine.amend(args.amend, args.text)
    elif args.rewrite is not None:
        if not args.text:
            _emit({"ok": False, "error": "--rewrite needs the new wording"})
            return 2
        result = engine.rewrite(args.rewrite, args.text)
    elif args.strike is not None:
        result = engine.strike(args.strike)
    elif args.unstrike is not None:
        result = engine.unstrike(args.unstrike)
    elif args.tear_out is not None:
        result = engine.tear_out(args.tear_out)
    elif args.text:
        result = engine.note(args.text)
    else:
        _emit(engine.notebook())
        return 0
    _emit(result)
    if result.get("ok"):
        _save(sealed, engine)
    return 0 if result.get("ok") else 1


def cmd_board(args) -> int:
    """The case board — conclusions with the evidence under them.

    Read-only and not a turn: reviewing your own reasoning is not an action.
    """
    _, engine = _open(args.case)
    _emit(engine.board())
    return 0


def cmd_cast(args) -> int:
    _, engine = _open(args.case)
    _emit(engine.cast_sheet())
    return 0


def cmd_frontier(args) -> int:
    _, engine = _open(args.case)
    _emit(engine.frontier())
    return 0


def cmd_hint(args) -> int:
    sealed, engine = _open(args.case)
    _emit(engine.hint())
    _close(sealed, engine)
    return 0


def cmd_accuse(args) -> int:
    sealed, engine = _open(args.case)
    _emit(engine.accuse(args.who, args.motive or "", args.method or "", args.evidence or []))
    _close(sealed, engine)
    return 0


def cmd_open_questions(args) -> int:
    """What conclusions exist that the player has not yet drawn.

    Narrator-only: used to map free-text player statements onto revelation ids.
    Returns ids and statements of *available* conclusions, which is a real
    spoiler surface — hence never rendered verbatim to the player.
    """
    _, engine = _open(args.case)
    case, st = engine.case, engine.state
    out = []
    for rev in case.revelations:
        if rev.id in st.held:
            continue
        if any(r not in st.held for r in rev.requires):
            continue
        out.append({
            "id": rev.id,
            "statement": rev.statement,
            "evidence_held": sum(1 for c in rev.clues if c in st.found),
            "evidence_needed": rev.support_needed,
        })
    _emit({
        "open_conclusions": out,
        "NARRATOR_ONLY":
            "Use this ONLY to match what the player just said to a conclusion id, then call "
            "`deduce`. Never list these to the player, never hint at how many there are, and "
            "never let an unmatched statement reveal that a conclusion exists.",
    })
    return 0


def cmd_status(args) -> int:
    sealed, engine = _open(args.case)
    st = engine.state
    _emit({
        "assist": st.assist,
        "turns": st.turns,
        "clues": f"{len(st.found)}/{len(engine.case.clues)}",
        "established": len(st.held),
        "hints_used": st.hints_used,
        "spoilers_taken": sealed.spoiler_count(),
        "accusations": st.accusations,
        "closed": st.closed,
    })
    return 0


def cmd_assist(args) -> int:
    sealed, engine = _open(args.case)
    engine.state.assist = args.level
    _save(sealed, engine)
    print(f"Assist level set to {args.level}.")
    return 0


def cmd_casebook(args) -> int:
    """The casebook — the player's own records, on pages they leaf through.

    Free and untimed, like the views it is built from. With `--page` it prints
    one page and exits, which is how the narrator reads a page out; with no
    arguments it opens the full-screen view, which the player drives.
    """
    _, engine = _open(args.case)
    if args.page:
        text = casebook.render(engine, args.page)
        if not text:
            print(f"no such page: {args.page}", file=sys.stderr)
            return 2
        print(text)
        return 0
    if not sys.stdout.isatty():
        # Piped, redirected, or run by a tool that captures output — including
        # Claude Code's own shell. There is no terminal to take over, so print
        # every page instead of failing, and say why the pages did not appear.
        print("The paged casebook needs a terminal to take over, and this "
              "output is being captured.\nRun it in a terminal of your own to "
              "leaf through it. All five pages follow.\n", file=sys.stderr)
        print("\n\n".join(casebook.render(engine, name)
                          for name in casebook.PAGE_NAMES))
        return 0
    return casebook.run(engine)


def cmd_scratch(args) -> int:
    """Copy a sealed case to `scratch/`, so development never targets a live one.

    Point `--case` at the copy and every write lands there:

        $ python3 -m mystery.cli scratch --case cases/pierhead
        { "case": "scratch/pierhead-1", ... }
        $ python3 -m mystery.cli deduce --case scratch/pierhead-1 --as-stated "..."

    The copy carries the same sealed case, key and play state, so it behaves
    exactly like the case it came from. `state.history.jsonl` is left behind:
    the copy starts its own.
    """
    sealed = SealedCase(args.case)
    if not sealed.exists():
        print(f"no sealed case at {args.case}", file=sys.stderr)
        raise SystemExit(2)
    slug = os.path.basename(os.path.normpath(args.case)) or "case"
    os.makedirs(SCRATCH_ROOT, exist_ok=True)
    n = 1
    while os.path.exists(os.path.join(SCRATCH_ROOT, f"{slug}-{n}")):
        n += 1
    dest = os.path.join(SCRATCH_ROOT, f"{slug}-{n}")
    shutil.copytree(args.case, dest,
                    ignore=shutil.ignore_patterns("state.history.jsonl"))
    _emit({"ok": True, "case": dest, "copied_from": args.case,
           "use": f"--case {dest}"})
    return 0


def cmd_undo(args) -> int:
    """Restore the state from before the last command that wrote one.

    A repair tool. Hidden from `--help` and absent from the play skill on
    purpose: see the docstring on `_save`.
    """
    sealed = SealedCase(args.case)
    if not sealed.exists():
        print(f"no sealed case at {args.case}", file=sys.stderr)
        raise SystemExit(2)
    hist = _history_path(sealed)
    lines = []
    if os.path.exists(hist):
        with open(hist, "r", encoding="utf-8") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    if not lines:
        _emit({"ok": False, "error": f"no recorded history for {args.case}"})
        return 1
    entry = json.loads(lines.pop())
    State(**entry["state"]).save(sealed.state_path)
    with open(hist, "w", encoding="utf-8") as fh:
        fh.write("".join(ln + "\n" for ln in lines))
    _emit({"ok": True, "undid": entry.get("cmd", []),
           "turns": entry["state"].get("turns"), "further_undos": len(lines)})
    return 0


def cmd_spoil(args) -> int:
    """Break the seal. Deliberately awkward."""
    sealed, engine = _open(args.case)
    if not args.yes:
        print("This reveals the solution and is recorded permanently in spoilers.log,")
        print("which the final grade reads. Re-run with --yes if you mean it.")
        return 1
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    sealed.record_spoiler(args.what, stamp)
    truth = engine.case.truth
    if args.what == "culprit":
        _emit({"culprit": truth.culprit})
    else:
        _emit({"culprit": truth.culprit, "motive": truth.motive, "method": truth.method,
               "weapon": truth.weapon, "narrative": truth.narrative})
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mystery", description="Sealed-truth mystery engine")
    # metavar, not the default brace list: argparse's generated list of choices
    # names every subcommand including the ones whose help is SUPPRESS, which
    # would put `undo` back in front of a narrator.
    sub = p.add_subparsers(dest="cmd", required=True, metavar="<command>")

    v = sub.add_parser("validate", help="run fair-play checks on a draft case")
    v.add_argument("draft")
    v.set_defaults(func=cmd_validate)

    s = sub.add_parser("seal", help="validate then encrypt a draft into a playable case")
    s.add_argument("draft")
    s.add_argument("--slug")
    s.add_argument("--assist", choices=ASSIST_LEVELS, default="watson")
    s.add_argument("--force", action="store_true")
    s.add_argument("--delete-draft", action="store_true")
    s.set_defaults(func=cmd_seal)

    def play(name, help_text=None):
        # No `help` at all, rather than help=SUPPRESS: argparse only leaves a
        # subcommand out of the listing when the keyword is absent, and prints
        # a literal "==SUPPRESS==" line when it is present and set to it.
        kwargs = {"help": help_text} if help_text is not None else {}
        q = sub.add_parser(name, **kwargs)
        q.add_argument("--case", required=True, help="path to the case directory")
        return q

    play("look", "describe the current place").set_defaults(func=cmd_look)
    play("search", "search the current place").set_defaults(func=cmd_search)
    play("journal", "the case file: clues found, conclusions held, and your own notes"
         ).set_defaults(func=cmd_journal)
    play("board", "your conclusions and the evidence under them").set_defaults(func=cmd_board)
    play("cast", "public dossier on everyone").set_defaults(func=cmd_cast)
    play("frontier", "what threads are open (shape only, no content)").set_defaults(func=cmd_frontier)
    play("hint", "escalating nudge, recorded in the grade").set_defaults(func=cmd_hint)
    play("status", "session summary").set_defaults(func=cmd_status)
    play("open-questions", "NARRATOR ONLY: map player statements to conclusions").set_defaults(func=cmd_open_questions)

    n = play("note", "write a line in your own notebook")
    n.add_argument("text", nargs="?", help="omit to read your notes back")
    n.add_argument("--strike", type=int, metavar="N",
                   help="rule a line through note N — it stays on the page, crossed out")
    n.add_argument("--unstrike", type=int, metavar="N",
                   help="take the rule back off note N")
    n.add_argument("--amend", type=int, metavar="N",
                   help="strike note N and write the given text underneath it")
    n.add_argument("--rewrite", type=int, metavar="N",
                   help="replace note N's wording in place, keeping its number and slot")
    n.add_argument("--tear-out", type=int, metavar="N", dest="tear_out",
                   help="remove note N from the page entirely (duplicates, typos)")
    n.set_defaults(func=cmd_note)

    g = play("go", "travel somewhere")
    g.add_argument("location")
    g.set_defaults(func=cmd_go)

    e = play("examine", "look closely at something")
    e.add_argument("thing")
    e.set_defaults(func=cmd_examine)

    a = play("ask", "question a character about a topic")
    a.add_argument("who")
    a.add_argument("topic")
    a.set_defaults(func=cmd_ask)

    d = play("deduce", "state a conclusion")
    d.add_argument("conclusion", nargs="?",
                   help="the matching conclusion id — omit when nothing matches")
    d.add_argument("--as-stated", dest="as_stated", required=True,
                   help="the player's own sentence, verbatim")
    d.add_argument("--evidence", nargs="*")
    d.set_defaults(func=cmd_deduce)

    ac = play("accuse", "name the culprit and close the case")
    ac.add_argument("who")
    ac.add_argument("--motive")
    ac.add_argument("--method")
    ac.add_argument("--evidence", nargs="*")
    ac.set_defaults(func=cmd_accuse)

    al = play("assist", "change how much the game thinks for you")
    al.add_argument("level", choices=ASSIST_LEVELS)
    al.set_defaults(func=cmd_assist)

    # Both are for whoever owns the repo, and both are kept out of `--help`,
    # because everything a narrator can see it will eventually offer the
    # player. `undo` in a player's hands takes back a spent hint or a failed
    # accusation, and the grade stops meaning anything; `scratch` is an answer
    # to a question no player has. CLAUDE.md documents them.
    cb = play("casebook", "your own records, on pages you can leaf through")
    cb.add_argument("--page", choices=casebook.PAGE_NAMES,
                    help="print one page instead of opening the full-screen view")
    cb.set_defaults(func=cmd_casebook)

    play("scratch").set_defaults(func=cmd_scratch)
    play("undo").set_defaults(func=cmd_undo)

    sp = play("spoil", "break the seal (recorded)")
    sp.add_argument("what", choices=["culprit", "everything"])
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(func=cmd_spoil)

    return p


def main(argv=None) -> int:
    global _INVOCATION
    _INVOCATION = list(argv) if argv is not None else sys.argv[1:]
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
