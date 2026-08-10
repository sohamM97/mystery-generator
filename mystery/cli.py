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
import sys

from .schema import Case, ASSIST_LEVELS
from .seal import SealedCase
from .engine import Engine, State
from .validate import validate

CASES_ROOT = "cases"


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


def _close(sealed: SealedCase, engine: Engine) -> None:
    engine.state.turns += 1
    engine.state.turns_since_progress += 1
    engine.state.save(sealed.state_path)


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
    sealed, engine = _open(args.case)
    _emit(engine.deduce(args.conclusion, args.evidence or []))
    _close(sealed, engine)
    return 0


def cmd_journal(args) -> int:
    _, engine = _open(args.case)
    _emit(engine.journal())
    return 0


def cmd_note(args) -> int:
    """Write a line in the player's notebook, or read the notebook back.

    Deliberately not a turn: thinking on paper costs the detective nothing, and
    charging for it would teach the player not to do it.
    """
    sealed, engine = _open(args.case)
    if args.text:
        _emit(engine.note(args.text))
        engine.state.save(sealed.state_path)
    else:
        _emit(engine.notebook())
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
    engine.state.save(sealed.state_path)
    print(f"Assist level set to {args.level}.")
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
    sub = p.add_subparsers(dest="cmd", required=True)

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

    def play(name, help_text):
        q = sub.add_parser(name, help=help_text)
        q.add_argument("--case", required=True, help="path to the case directory")
        return q

    play("look", "describe the current place").set_defaults(func=cmd_look)
    play("search", "search the current place").set_defaults(func=cmd_search)
    play("journal", "the detective's notebook").set_defaults(func=cmd_journal)
    play("cast", "public dossier on everyone").set_defaults(func=cmd_cast)
    play("frontier", "what threads are open (shape only, no content)").set_defaults(func=cmd_frontier)
    play("hint", "escalating nudge, recorded in the grade").set_defaults(func=cmd_hint)
    play("status", "session summary").set_defaults(func=cmd_status)
    play("open-questions", "NARRATOR ONLY: map player statements to conclusions").set_defaults(func=cmd_open_questions)

    n = play("note", "write a line in your own notebook")
    n.add_argument("text", nargs="?", help="omit to read your notes back")
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
    d.add_argument("conclusion")
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

    sp = play("spoil", "break the seal (recorded)")
    sp.add_argument("what", choices=["culprit", "everything"])
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(func=cmd_spoil)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
