"""The casebook: everything the player has earned, on pages they can leaf through.

This module adds no knowledge. Every page is built from a view the player can
already ask for free — `cast`, `journal`, `board`, `note`, `frontier` — so
opening the casebook can never show them something they have not already got.
Two consequences worth keeping:

- `narrator_guidance` is written for the narrator and is never shown to the
  player. Pages are assembled field by field, never by dumping a view, so a
  guidance string cannot arrive on a page by accident.
- The pages inherit the assist level from the views they are built on. On
  `holmes` the board carries no supporting evidence and `frontier` reports no
  count of conclusions that would land, so the casebook shows neither.

Reading is not an action: nothing here writes state or spends a turn.
"""

from __future__ import annotations

import textwrap

from .engine import Engine

WIDTH = 78


def _wrap(text: str, indent: str = "", width: int = WIDTH) -> list[str]:
    if not text:
        return []
    return textwrap.wrap(text, width=width,
                         initial_indent=indent, subsequent_indent=indent) or [indent.rstrip()]


def _bullet(text: str, indent: str = "  ") -> list[str]:
    """A `·` item whose continuation lines hang under its text, not its dot."""
    return textwrap.wrap(text, width=WIDTH,
                         initial_indent=f"{indent}· ",
                         subsequent_indent=f"{indent}  ")


def _rule(label: str) -> list[str]:
    return [label, "─" * min(len(label), WIDTH)]


def _cast_page(engine: Engine) -> list[str]:
    lines: list[str] = []
    for person in engine.cast_sheet()["cast"]:
        # Age and gender are absent unless the author recorded them, so the
        # header is built from whichever parts exist.
        facts = [person[k] for k in ("age", "gender") if person.get(k)]
        head = person["name"]
        if person.get("role"):
            head += f" — {person['role']}"
        if facts:
            head += f" ({', '.join(facts)})"
        lines += _wrap(head)
        lines += _wrap(person["known"], indent="    ")
        lines.append("")
    return lines or ["Nobody yet."]


def _notebook_page(engine: Engine) -> list[str]:
    notes = engine.notebook()["notes"]
    if not notes:
        return ["Your notebook is empty.",
                "",
                "Anything you write is yours alone — the case never reads it,",
                "and writing a line is free."]
    lines: list[str] = []
    for note in notes:
        # A struck line stays on the page. Hiding what the player stopped
        # believing would edit their reasoning for them.
        mark = "×" if note.get("struck") else " "
        body = note["text"]
        if note.get("struck"):
            body = f"[struck] {body}"
        lines += _wrap(f"{mark} {note['n']:>2}. {body}", )
        if note.get("replaces"):
            lines += _wrap(f"replaces note {note['replaces']}", indent="      ")
    return lines


def _conclusions_page(engine: Engine) -> list[str]:
    board = engine.board()
    lines: list[str] = []
    if not board["established"]:
        lines += ["You have concluded nothing yet.", ""]
    for item in board["established"]:
        lines += _wrap(item["statement"])
        who = "your own reasoning" if item["drawn_by"] == "you" else "drawn for you by the game"
        lines += _wrap(f"({who})", indent="    ")
        # Absent on holmes, which gives conclusions without the evidence.
        for clue in item.get("because", []):
            lines += _bullet(clue["headline"], indent="    ")
        lines.append("")

    if board.get("suspicions"):
        lines += _rule("Said aloud, not proved")
        for said in board["suspicions"]:
            lines += _bullet(said["text"])
        lines.append("")

    if board.get("unattached_clues"):
        lines += _rule("Loose ends — held, and attached to nothing")
        for clue in board["unattached_clues"]:
            lines += _bullet(clue["headline"])
    return lines


def _evidence_page(engine: Engine) -> list[str]:
    journal = engine.journal()
    if not journal["clues"]:
        return ["Nothing in the case file yet."]
    lines: list[str] = []
    for clue in journal["clues"]:
        lines += _wrap(f"[{clue['kind']}] {clue['headline']}")
        lines += _wrap(clue["detail"], indent="    ")
        lines.append("")
    lines += [journal["progress"]]
    return lines


def _threads_page(engine: Engine) -> list[str]:
    front = engine.frontier()
    lines: list[str] = []
    lines += _rule("Places")
    for place in front["places_with_loose_ends"]:
        seen = "" if place["visited"] else "  (never been)"
        lines += _bullet(f"{place['place']} — {place['loose_ends']} left{seen}")
    if not front["places_with_loose_ends"]:
        lines += ["  Nothing left where you can reach."]
    lines.append("")
    lines += _rule("People")
    for person in front["people_with_more_to_say"]:
        threads = person["threads"]
        word = "thread" if threads == 1 else "threads"
        lines += _bullet(f"{person['person']} — {threads} {word} unpulled")
    if not front["people_with_more_to_say"]:
        lines += ["  Nobody has anything left to say."]
    lines.append("")
    lines += [f"{front['clues_found']} of {front['clues_total']} clues found."]
    # Absent on holmes, where whether the evidence is already enough is the
    # player's judgement to make.
    if "conclusions_you_could_already_draw" in front:
        n = front["conclusions_you_could_already_draw"]
        lines += [f"Conclusions your evidence would already carry: {n}."]
    return lines


PAGES = [
    ("cast", "Who is who", _cast_page),
    ("evidence", "The case file", _evidence_page),
    ("conclusions", "What you have concluded", _conclusions_page),
    ("notebook", "Your notebook", _notebook_page),
    ("threads", "What you have not pulled", _threads_page),
]

PAGE_NAMES = [name for name, _, _ in PAGES]


def pages(engine: Engine) -> list[tuple[str, str, list[str]]]:
    """Every page as (name, title, lines). No state is written."""
    return [(name, title, build(engine)) for name, title, build in PAGES]


def render(engine: Engine, name: str) -> str:
    """One page as plain text, for printing outside the full-screen view."""
    for page_name, title, body in pages(engine):
        if page_name == name:
            return "\n".join([title, "═" * len(title), ""] + body)
    return ""


def run(engine: Engine) -> int:
    """The full-screen casebook. Left/right to leaf, up/down to scroll, q to close.

    Imported here rather than at module load: everything above works without a
    terminal, and the test suite builds pages on a machine with no tty.
    """
    import curses

    def read_key(screen, curses):
        """One keystroke, with arrow keys folded into a single KEY_* code.

        `keypad(True)` is meant to do this, and on most terminals it does. On
        some it doesn't, and `getch` hands back the three bytes an arrow key
        actually sends — 27, then `[`, then a letter — which would leave the
        arrows dead. Reading the tail ourselves covers both.
        """
        key = screen.getch()
        if key != 27:
            return key
        screen.nodelay(True)
        try:
            nxt = screen.getch()
            if nxt != ord("["):
                # A bare escape, or escape followed by something else. Put the
                # something else back: swallowing it loses a real keystroke,
                # and if that keystroke was `q` the casebook never closes.
                if nxt != -1:
                    curses.ungetch(nxt)
                return -1
            return {ord("C"): curses.KEY_RIGHT, ord("D"): curses.KEY_LEFT,
                    ord("A"): curses.KEY_UP, ord("B"): curses.KEY_DOWN}.get(
                        screen.getch(), -1)
        finally:
            screen.nodelay(False)

    built = pages(engine)

    def loop(screen):
        curses.curs_set(0)
        # Fold the escape sequence an arrow key sends into a single KEY_LEFT /
        # KEY_RIGHT. Without it getch returns the bare escape and the arrows
        # do nothing at all.
        screen.keypad(True)
        page, top = 0, 0
        while True:
            screen.erase()
            height, width = screen.getmaxyx()
            name, title, body = built[page]
            tabs = "  ".join(
                f"[{t.upper()}]" if i == page else f" {t} "
                for i, (t, _, _) in enumerate(built)
            )
            screen.addnstr(0, 0, tabs, width - 1, curses.A_BOLD)
            screen.addnstr(1, 0, title, width - 1)
            screen.addnstr(2, 0, "─" * (width - 1), width - 1)

            window = height - 5  # tabs, title, rule, and the footer
            top = max(0, min(top, max(0, len(body) - window)))
            for row, line in enumerate(body[top:top + window]):
                screen.addnstr(3 + row, 0, line, width - 1)

            more = "  ↑↓ scroll" if len(body) > window else ""
            screen.addnstr(height - 1, 0,
                           f"←→ pages{more}   q close   ({page + 1}/{len(built)})",
                           width - 1, curses.A_DIM)
            screen.refresh()

            key = read_key(screen, curses)
            # `q` only. An arrow key is escape, `[`, letter — `read_key` folds
            # that into a KEY_LEFT, but a bare escape must not close the
            # casebook or the arrows would shut it on some terminals.
            if key == ord("q"):
                return
            if key in (curses.KEY_RIGHT, ord("l"), ord("\t")):
                page, top = (page + 1) % len(built), 0
            elif key in (curses.KEY_LEFT, ord("h")):
                page, top = (page - 1) % len(built), 0
            elif key in (curses.KEY_DOWN, ord("j")):
                top += 1
            elif key in (curses.KEY_UP, ord("k")):
                top -= 1
            elif key == curses.KEY_NPAGE:
                top += window
            elif key == curses.KEY_PPAGE:
                top -= window

    curses.wrapper(loop)
    return 0
