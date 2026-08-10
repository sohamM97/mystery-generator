"""Fair-play validation.

A generated mystery is not trusted until it passes here. These checks encode
Knox's Decalogue, Van Dine's rules, and Justin Alexander's Three Clue Rule as
things a machine can actually verify, plus a solvability simulation that plays
the case as a perfect detective and confirms the truth is reachable.

This is the load-bearing answer to "the narrator must not forget or contradict
itself". The narrator does not remember the case — it queries it — and the case
was proven consistent before play began.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .schema import Case, CLUE_KINDS, RELIABILITY

# Knox #1: the culprit must be someone the reader has met early. Expressed as a
# fraction of the acts in the case.
CULPRIT_INTRO_FRACTION = 0.34
# Alexander: three clues for anything you actually need the player to conclude.
CRITICAL_CLUE_MINIMUM = 3
SUPPORTING_CLUE_MINIMUM = 2


@dataclass
class Issue:
    level: str  # "error" | "warn"
    code: str
    message: str

    def __str__(self) -> str:
        mark = "✗" if self.level == "error" else "!"
        return f"  {mark} [{self.code}] {self.message}"


class Report:
    def __init__(self) -> None:
        self.issues: list[Issue] = []
        self.notes: list[str] = []

    def error(self, code: str, message: str) -> None:
        self.issues.append(Issue("error", code, message))

    def warn(self, code: str, message: str) -> None:
        self.issues.append(Issue("warn", code, message))

    def note(self, message: str) -> None:
        self.notes.append(message)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warn"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        lines = []
        if self.errors:
            lines.append(f"ERRORS ({len(self.errors)}) — case is unfair or unsolvable:")
            lines += [str(i) for i in self.errors]
        if self.warnings:
            lines.append(f"WARNINGS ({len(self.warnings)}):")
            lines += [str(i) for i in self.warnings]
        if self.notes:
            lines.append("Analysis:")
            lines += [f"  · {n}" for n in self.notes]
        if self.ok and not self.warnings:
            lines.append("Clean. The case is fair and solvable.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Reachability simulation
# ---------------------------------------------------------------------------


def simulate(case: Case) -> tuple[set[str], set[str]]:
    """Play the case as a perfect detective who never misses anything.

    Returns (clues found, revelations reached). Anything outside these sets is
    unreachable content: the player physically cannot get to it, which means a
    soft-lock if it was needed and dead weight if it was not.
    """
    found: set[str] = set()
    held: set[str] = set()
    open_locations = {l.id for l in case.locations if not l.gates}

    while True:
        grew = False

        # Collect everything now available.
        for clue in case.clues:
            if clue.id in found:
                continue
            if any(g not in held for g in clue.gates):
                continue
            # A clue tied to a place needs that place to be reachable.
            where = clue.source.at
            if where and where not in open_locations:
                continue
            found.add(clue.id)
            grew = True

        # Draw every inference the evidence now supports.
        for rev in case.revelations:
            if rev.id in held:
                continue
            if any(r not in held for r in rev.requires):
                continue
            have = sum(1 for c in rev.clues if c in found)
            if have >= min(rev.support_needed, len(rev.clues) or 1) and have > 0:
                held.add(rev.id)
                grew = True

        # New understanding may open new ground.
        for loc in case.locations:
            if loc.id not in open_locations and all(g in held for g in loc.gates):
                open_locations.add(loc.id)
                grew = True

        if not grew:
            return found, held


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _check_references(case: Case, rep: Report) -> None:
    char_ids = {c.id for c in case.cast}
    loc_ids = {l.id for l in case.locations}
    clue_ids = {c.id for c in case.clues}
    rev_ids = {r.id for r in case.revelations}

    for ids, label in ((char_ids, "character"), (loc_ids, "location"),
                       (clue_ids, "clue"), (rev_ids, "revelation")):
        if len(ids) != len(list(ids)):  # pragma: no cover - set built from list
            rep.error("DUP_ID", f"duplicate {label} ids")

    for lst, label in ((case.cast, "character"), (case.locations, "location"),
                       (case.clues, "clue"), (case.revelations, "revelation")):
        seen: set[str] = set()
        for item in lst:
            if item.id in seen:
                rep.error("DUP_ID", f"duplicate {label} id {item.id!r}")
            seen.add(item.id)

    for loc in case.locations:
        for other in loc.connects:
            if other not in loc_ids:
                rep.error("BAD_REF", f"location {loc.id!r} connects to unknown {other!r}")
        for g in loc.gates:
            if g not in rev_ids:
                rep.error("BAD_REF", f"location {loc.id!r} gated on unknown revelation {g!r}")

    for clue in case.clues:
        if clue.kind not in CLUE_KINDS:
            rep.error("BAD_KIND", f"clue {clue.id!r} has unknown kind {clue.kind!r}")
        if clue.reliability not in RELIABILITY:
            rep.error("BAD_KIND", f"clue {clue.id!r} has unknown reliability {clue.reliability!r}")
        if clue.source.at and clue.source.at not in loc_ids:
            rep.error("BAD_REF", f"clue {clue.id!r} sourced at unknown location {clue.source.at!r}")
        if clue.source.kind == "ask" and clue.source.ref not in char_ids:
            rep.error("BAD_REF", f"clue {clue.id!r} asks unknown character {clue.source.ref!r}")
        for g in clue.gates:
            if g not in rev_ids:
                rep.error("BAD_REF", f"clue {clue.id!r} gated on unknown revelation {g!r}")
        for s in clue.supports:
            if s not in rev_ids:
                rep.error("BAD_REF", f"clue {clue.id!r} supports unknown revelation {s!r}")
        for d in clue.debunked_by:
            if d not in clue_ids:
                rep.error("BAD_REF", f"clue {clue.id!r} debunked by unknown clue {d!r}")

    for rev in case.revelations:
        for r in rev.requires:
            if r not in rev_ids:
                rep.error("BAD_REF", f"revelation {rev.id!r} requires unknown {r!r}")
        for c in rev.clues:
            if c not in clue_ids:
                rep.error("BAD_REF", f"revelation {rev.id!r} cites unknown clue {c!r}")

    for ev in case.timeline:
        if ev.actor not in char_ids:
            rep.error("BAD_REF", f"timeline event at t={ev.t} has unknown actor {ev.actor!r}")
        if ev.location not in loc_ids:
            rep.error("BAD_REF", f"timeline event at t={ev.t} in unknown location {ev.location!r}")
        for w in ev.witnesses:
            if w not in char_ids:
                rep.error("BAD_REF", f"timeline event at t={ev.t} has unknown witness {w!r}")
        if ev.trace and ev.trace not in clue_ids:
            rep.error("BAD_REF", f"timeline event at t={ev.t} leaves unknown clue {ev.trace!r}")

    if case.truth.culprit not in char_ids:
        rep.error("BAD_REF", f"culprit {case.truth.culprit!r} is not in the cast")
    for a in case.truth.accomplices:
        if a not in char_ids:
            rep.error("BAD_REF", f"accomplice {a!r} is not in the cast")
    for fs in case.false_solutions:
        if fs.culprit not in char_ids:
            rep.error("BAD_REF", f"false solution {fs.id!r} names unknown {fs.culprit!r}")
        for c in fs.refuted_by:
            if c not in clue_ids:
                rep.error("BAD_REF", f"false solution {fs.id!r} refuted by unknown clue {c!r}")


def _check_dag(case: Case, rep: Report) -> None:
    """Revelations must form a DAG — no circular reasoning."""
    colour: dict[str, int] = {}

    def visit(rid: str, stack: list[str]) -> None:
        state = colour.get(rid, 0)
        if state == 1:
            cycle = " -> ".join(stack[stack.index(rid):] + [rid])
            rep.error("CYCLE", f"circular reasoning in revelations: {cycle}")
            return
        if state == 2:
            return
        colour[rid] = 1
        rev = case.revelation(rid)
        if rev:
            for dep in rev.requires:
                visit(dep, stack + [rid])
        colour[rid] = 2

    for rev in case.revelations:
        visit(rev.id, [])


def _check_three_clue_rule(case: Case, rep: Report) -> None:
    for rev in case.revelations:
        # Only count clues that actually declare they support this. A one-way
        # link means the author changed their mind halfway.
        cited = set(rev.clues)
        declared = {c.id for c in case.clues if rev.id in c.supports}
        if cited != declared:
            missing = declared - cited
            extra = cited - declared
            if missing:
                rep.warn("LINK_ASYMMETRY",
                         f"clues {sorted(missing)} support {rev.id!r} but it does not cite them")
            if extra:
                rep.error("LINK_ASYMMETRY",
                          f"revelation {rev.id!r} cites {sorted(extra)} which do not support it")

        hard = [c for c in (case.clue(x) for x in rev.clues) if c and c.reliability != "false"]
        minimum = CRITICAL_CLUE_MINIMUM if rev.critical else SUPPORTING_CLUE_MINIMUM
        if len(hard) < minimum:
            level = rep.error if rev.critical else rep.warn
            level("THREE_CLUE",
                  f"revelation {rev.id!r} ({'critical' if rev.critical else 'supporting'}) "
                  f"has {len(hard)} trustworthy clue(s), needs {minimum}")

        if rev.support_needed > len(rev.clues):
            rep.error("UNSATISFIABLE",
                      f"revelation {rev.id!r} needs {rev.support_needed} clues "
                      f"but only {len(rev.clues)} exist")

        # Don't let one location or one witness carry a critical conclusion —
        # if the player misses that room, the case dead-ends.
        if rev.critical and hard:
            sources = {(c.source.kind, c.source.at or c.source.ref) for c in hard}
            if len(sources) == 1:
                rep.warn("SINGLE_SOURCE",
                         f"every clue for critical revelation {rev.id!r} comes from the same "
                         f"place — a player who skips it is stuck")


def _check_knox(case: Case, rep: Report) -> None:
    acts = max([c.introduced_at for c in case.cast] + [0]) + 1
    culprit = case.character(case.truth.culprit)
    if culprit:
        cutoff = max(0, math.floor(acts * CULPRIT_INTRO_FRACTION))
        if culprit.introduced_at > cutoff:
            rep.error("KNOX_1",
                      f"culprit {culprit.name} first appears in act {culprit.introduced_at} of "
                      f"{acts}; the reader must meet them by act {cutoff}")

    # Knox #4 / Van Dine #14: the method must be clued, not asserted. Something
    # in the evidence has to point at how it was done.
    method_revs = [r for r in case.revelations if r.critical and "method" in r.id.lower()]
    if not method_revs:
        rep.warn("KNOX_4",
                 "no critical revelation about the method — the player can name a culprit "
                 "without ever understanding how the crime was done")

    for conceit in case.conceits:
        rep.note(f"declared conceit: {conceit} (validator expects it to be clued)")

    lone_suspects = len(case.cast)
    if lone_suspects < 4:
        rep.warn("THIN_CAST", f"only {lone_suspects} characters — the culprit is guessable by elimination")


def _check_solvability(case: Case, rep: Report) -> None:
    found, held = simulate(case)

    orphan_clues = [c.id for c in case.clues if c.id not in found]
    if orphan_clues:
        rep.error("UNREACHABLE",
                  f"clues can never be found: {sorted(orphan_clues)} — check their gates "
                  f"and the locations they sit in")

    orphan_revs = [r.id for r in case.revelations if r.id not in held]
    for rid in orphan_revs:
        rev = case.revelation(rid)
        level = rep.error if (rev and rev.critical) else rep.warn
        level("UNREACHABLE", f"revelation {rid!r} can never be reached even by a perfect detective")

    critical = [r for r in case.revelations if r.critical]
    if not critical:
        rep.error("NO_SOLUTION", "no revelation is marked critical — the case has no solution chain")
    else:
        rep.note(f"solution chain: {len(critical)} critical revelations, "
                 f"{len(found)}/{len(case.clues)} clues reachable")

    unreachable_locs = set()
    open_locs = {l.id for l in case.locations if not l.gates}
    for loc in case.locations:
        if loc.id not in open_locs and any(g not in held for g in loc.gates):
            unreachable_locs.add(loc.id)
    if unreachable_locs:
        rep.error("UNREACHABLE", f"locations can never be entered: {sorted(unreachable_locs)}")

    # Every red herring needs an honest way out. An unrefutable false lead is a
    # cheat, not a mystery.
    for clue in case.clues:
        if clue.reliability == "false" and not clue.debunked_by:
            rep.error("UNFAIR_HERRING",
                      f"clue {clue.id!r} is false but nothing debunks it — the player can never "
                      f"know it was a lie")
        for d in clue.debunked_by:
            if d not in found:
                rep.error("UNFAIR_HERRING",
                          f"clue {clue.id!r} is debunked only by {d!r}, which is unreachable")

    for fs in case.false_solutions:
        if not fs.refuted_by:
            rep.error("UNFAIR_ALT",
                      f"false solution {fs.id!r} has no refutation — a player who accuses "
                      f"{fs.culprit} can never be shown why they were wrong")
        for c in fs.refuted_by:
            if c not in found:
                rep.error("UNFAIR_ALT", f"false solution {fs.id!r} is refuted by unreachable clue {c!r}")
        if fs.culprit == case.truth.culprit:
            rep.error("UNFAIR_ALT", f"false solution {fs.id!r} names the actual culprit")

    if len(case.false_solutions) < 2:
        rep.warn("THIN_ALTS",
                 f"only {len(case.false_solutions)} alternative solution(s) — accusing is a "
                 f"formality rather than a judgement")


def _check_timeline(case: Case, rep: Report) -> None:
    by_actor: dict[str, list] = {}
    for ev in case.timeline:
        by_actor.setdefault(ev.actor, []).append(ev)

    for actor, events in by_actor.items():
        events.sort(key=lambda e: e.t)
        for a, b in zip(events, events[1:]):
            if a.t == b.t and a.location != b.location:
                name = case.character(actor)
                rep.error("TIMELINE",
                          f"{name.name if name else actor} is in two places at t={a.t}: "
                          f"{a.location} and {b.location}")

    if case.timeline:
        culprit_events = by_actor.get(case.truth.culprit, [])
        at_scene = [e for e in culprit_events if e.t == case.truth.time]
        window = [e for e in culprit_events if abs(e.t - case.truth.time) <= 30]
        if not at_scene and not window:
            rep.error("NO_OPPORTUNITY",
                      f"the culprit has no timeline event within 30 minutes of the crime at "
                      f"t={case.truth.time} — they had no opportunity")

    # Anyone the timeline places elsewhere during the crime has a real alibi.
    # That is fine, but it should be discoverable, not just true.
    rep.note(f"timeline: {len(case.timeline)} events across {len(by_actor)} actors")


def validate(case: Case) -> Report:
    rep = Report()
    _check_references(case, rep)
    if rep.errors:
        # Later checks assume references resolve; bail with what we have.
        rep.note("reference errors block the remaining checks — fix these first")
        return rep
    _check_dag(case, rep)
    _check_three_clue_rule(case, rep)
    _check_knox(case, rep)
    _check_timeline(case, rep)
    _check_solvability(case, rep)
    return rep
