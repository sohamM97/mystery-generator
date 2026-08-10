"""The play engine.

Everything the narrator says about facts comes from here. The narrator supplies
voice, pacing, and atmosphere; the engine supplies truth. That split is what
stops the story from drifting: an LLM asked to *remember* a mystery over fifty
turns will contradict itself, an LLM asked to *describe this JSON* will not.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict

from .schema import Case, Clue, ASSIST_LEVELS


@dataclass
class State:
    assist: str = "watson"
    at: str = ""  # current location id
    found: list[str] = field(default_factory=list)  # clue ids
    held: list[str] = field(default_factory=list)  # revelation ids
    hunches: list[str] = field(default_factory=list)  # believed but unevidenced
    visited: list[str] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)  # source keys already used
    turns: int = 0
    turns_since_progress: int = 0
    hints_used: int = 0
    accusations: list[dict] = field(default_factory=list)
    closed: bool = False

    @staticmethod
    def load(path: str) -> "State":
        with open(path, "r", encoding="utf-8") as fh:
            return State(**json.load(fh))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=2)


class Engine:
    def __init__(self, case: Case, state: State):
        self.case = case
        self.state = state
        if not self.state.at:
            self.state.at = case.locations[0].id
            self.state.visited.append(self.state.at)

    # -- knowledge ---------------------------------------------------------

    def holds(self, rid: str) -> bool:
        return rid in self.state.held

    def clue_available(self, clue: Clue) -> bool:
        if any(g not in self.state.held for g in clue.gates):
            return False
        if clue.source.at and clue.source.at not in self.reachable_locations():
            return False
        return True

    def reachable_locations(self) -> set[str]:
        return {
            l.id for l in self.case.locations
            if all(g in self.state.held for g in l.gates)
        }

    def _record(self, clue: Clue) -> bool:
        """Add a clue to the journal. Returns True if it was new."""
        if clue.id in self.state.found:
            return False
        self.state.found.append(clue.id)
        self.state.turns_since_progress = 0
        return True

    def auto_infer(self) -> list[str]:
        """Draw the inferences the current assist level hands to the player.

        holmes   nothing. You connect every dot yourself.
        watson   the plumbing — non-critical steps — resolves on its own, so you
                 spend your attention on the conclusions that matter.
        lestrade everything the evidence supports, Danganronpa-style: the game
                 voices the deduction and you follow the thread.
        """
        if self.state.assist == "holmes":
            return []
        gained: list[str] = []
        while True:
            grew = False
            for rev in self.case.revelations:
                if rev.id in self.state.held:
                    continue
                if self.state.assist == "watson" and rev.critical:
                    continue
                if any(r not in self.state.held for r in rev.requires):
                    continue
                have = sum(1 for c in rev.clues if c in self.state.found)
                if have >= rev.support_needed:
                    self.state.held.append(rev.id)
                    gained.append(rev.id)
                    grew = True
            if not grew:
                return gained

    # -- actions -----------------------------------------------------------

    def look(self) -> dict:
        loc = self.case.location(self.state.at)
        assert loc is not None
        reachable = self.reachable_locations()
        here = [c for c in self.case.clues
                if c.source.at == loc.id and self.clue_available(c)]
        people = self._people_at(loc.id)
        return {
            "location": loc.name,
            "description": loc.desc,
            "exits": [
                {"id": x, "name": n.name}
                for x in loc.connects
                if x in reachable and (n := self.case.location(x))
            ],
            "people_here": people,
            "examinable": sorted({c.source.ref for c in here if c.source.kind == "examine"}),
            "searchable": any(c.source.kind == "search" for c in here),
            "unfound_here": sum(1 for c in here if c.id not in self.state.found),
        }

    def _people_at(self, loc_id: str) -> list[dict]:
        """Who can be spoken to here, derived from clue sources.

        Characters live where their testimony lives — no separate placement to
        drift out of sync with the clue table.
        """
        ids = {
            c.source.ref for c in self.case.clues
            if c.source.kind == "ask" and c.source.at in ("", loc_id)
        }
        out = []
        for cid in sorted(ids):
            ch = self.case.character(cid)
            if ch:
                out.append({"id": ch.id, "name": ch.name, "role": ch.role})
        return out

    def travel(self, loc_id: str) -> dict:
        loc = self.case.location(loc_id)
        if not loc:
            return {"ok": False, "error": f"no such place: {loc_id}"}
        if loc_id not in self.reachable_locations():
            return {"ok": False, "error": "you have no reason to go there yet"}
        current = self.case.location(self.state.at)
        if current and loc_id not in current.connects and loc_id != self.state.at:
            # Allow fast travel between known places; the map is not a maze.
            if loc_id not in self.state.visited:
                return {"ok": False, "error": f"you don't know the way to {loc.name} from here"}
        self.state.at = loc_id
        if loc_id not in self.state.visited:
            self.state.visited.append(loc_id)
        return {"ok": True, **self.look()}

    def examine(self, ref: str) -> dict:
        return self._collect(f"examine:{self.state.at}:{ref}".lower(), f"You examine the {ref}.")

    def search(self) -> dict:
        return self._collect(f"search:{self.state.at}".lower(), "You search the room thoroughly.")

    def ask(self, char_id: str, topic: str) -> dict:
        ch = self.case.character(char_id)
        if not ch:
            return {"ok": False, "error": f"no such person: {char_id}"}
        for locked_topic, required in ch.locked_topics.items():
            if locked_topic.lower() in topic.lower() and required not in self.state.held:
                return {
                    "ok": True,
                    "deflection": True,
                    "speaker": ch.name,
                    "narrator_guidance":
                        f"{ch.name} will not discuss this yet. Play the refusal in character — "
                        f"evasion, not a locked door. Do not hint at what would unlock it.",
                    "new_clues": [],
                }
        return self._collect(f"ask:{char_id}:{topic}".lower(),
                             f"You put the question to {ch.name}.", speaker=ch.name)

    def _collect(self, source_key: str, flavour: str, speaker: str = "") -> dict:
        matches = self.case.clues_from(source_key)
        available = [c for c in matches if self.clue_available(c)]
        new: list[Clue] = []
        repeat: list[Clue] = []
        for clue in available:
            if self._record(clue):
                new.append(clue)
            else:
                repeat.append(clue)

        if source_key not in self.state.asked:
            self.state.asked.append(source_key)

        gained = self.auto_infer() if new else []
        withheld = [c for c in matches if not self.clue_available(c)]

        return {
            "ok": True,
            "flavour": flavour,
            "speaker": speaker,
            "new_clues": [self._clue_view(c) for c in new],
            "already_known": [c.headline for c in repeat],
            "nothing_here": not available,
            "inferences": [
                {"id": r, "statement": rv.statement}
                for r in gained if (rv := self.case.revelation(r))
            ],
            "narrator_guidance": self._guidance(new, withheld),
        }

    def _clue_view(self, clue: Clue) -> dict:
        """What the narrator is allowed to know about a clue.

        `reliability` and `hidden_note` ship to the narrator but are marked
        never-reveal: the narrator needs them to keep a liar lying consistently
        across the whole case, which is exactly the failure mode we're
        engineering against. It must never surface them to the player.
        """
        return {
            "id": clue.id,
            "kind": clue.kind,
            "headline": clue.headline,
            "detail": clue.detail,
            "NEVER_REVEAL": {
                "reliability": clue.reliability,
                "note": clue.hidden_note,
                "instruction":
                    "Deliver this clue exactly as written. If reliability is 'false' or 'soft', "
                    "present it with full confidence anyway — the player's job is to catch it. "
                    "Never state or imply the reliability. Stay consistent with the note on "
                    "every future retelling.",
            },
        }

    def _guidance(self, new: list[Clue], withheld: list[Clue]) -> str:
        bits = []
        if not new and withheld:
            bits.append(
                "There is more here, but the detective doesn't yet know enough to see it. "
                "Describe the scene as unremarkable — do not signal that something is hidden."
            )
        if not new and not withheld:
            bits.append("Nothing to find. Say so in one line and don't pad it.")
        return " ".join(bits)

    # -- deduction ---------------------------------------------------------

    def deduce(self, rid: str, evidence: list[str] | None = None) -> dict:
        """The player states a conclusion. The engine rules on whether they've
        earned it.

        Obra Dinn's lesson: confirm, but don't make confirmation cheap. You can
        be right without grounds — the engine records that as a hunch, and the
        final grade counts it separately from a proved conclusion.
        """
        rev = self.case.revelation(rid)
        if not rev:
            return {"ok": False, "error": f"no such conclusion: {rid}"}
        if rid in self.state.held:
            return {"ok": True, "already": True, "statement": rev.statement}

        missing_prereq = [r for r in rev.requires if r not in self.state.held]
        if missing_prereq:
            return {
                "ok": False,
                "premature": True,
                "narrator_guidance":
                    "The leap is too far — something earlier is still unestablished. Say so as "
                    "the detective feeling the gap, and name the *area* that's shaky, not the "
                    "missing conclusion itself.",
            }

        cited = [e for e in (evidence or []) if e in self.state.found]
        supporting = [c for c in rev.clues if c in self.state.found]
        # Cited evidence is checked against the case, so you can't wave at
        # unrelated clues and call it proof.
        valid_citations = [c for c in cited if c in rev.clues]

        if len(supporting) >= rev.support_needed:
            self.state.held.append(rid)
            self.state.turns_since_progress = 0
            cascade = self.auto_infer()
            newly_open = [
                l.name for l in self.case.locations
                if rid in l.gates and all(g in self.state.held for g in l.gates)
            ]
            return {
                "ok": True,
                "accepted": True,
                "statement": rev.statement,
                "evidence_held": supporting,
                "weak_citation": bool(evidence) and not valid_citations,
                "cascade": [
                    {"id": r, "statement": rv.statement}
                    for r in cascade if (rv := self.case.revelation(r))
                ],
                "opened": newly_open,
                "narrator_guidance":
                    "Confirm it. Let the detective feel the click. If `opened` is non-empty, "
                    "make the new ground feel like a consequence of the thought, not a reward.",
            }

        if rid not in self.state.hunches:
            self.state.hunches.append(rid)
        return {
            "ok": True,
            "accepted": False,
            "hunch": True,
            "have": len(supporting),
            "need": rev.support_needed,
            "narrator_guidance":
                "The instinct may be right but it isn't proved. Do NOT say whether it's correct. "
                "Have the detective note it as a suspicion and observe that it wouldn't hold up "
                "to a hostile question yet.",
        }

    # -- guidance ----------------------------------------------------------

    def frontier(self) -> dict:
        """The Outer Wilds ship-log view: what you know that you haven't chased.

        Shows shape, never content. 'Three threads open, one of them at the
        boathouse' — not what's at the boathouse.
        """
        reachable = self.reachable_locations()
        open_threads = []
        for loc in self.case.locations:
            if loc.id not in reachable:
                continue
            pending = [c for c in self.case.clues
                       if c.source.at == loc.id and c.id not in self.state.found
                       and self.clue_available(c)]
            if pending:
                open_threads.append({"place": loc.name, "loose_ends": len(pending),
                                     "visited": loc.id in self.state.visited})

        unasked = []
        for ch in self.case.cast:
            topics = {c.source.topic for c in self.case.clues
                      if c.source.kind == "ask" and c.source.ref == ch.id
                      and c.id not in self.state.found and self.clue_available(c)}
            if topics:
                unasked.append({"person": ch.name, "threads": len(topics)})

        ripe = []
        for rev in self.case.revelations:
            if rev.id in self.state.held or any(r not in self.state.held for r in rev.requires):
                continue
            have = sum(1 for c in rev.clues if c in self.state.found)
            if have >= rev.support_needed:
                ripe.append(rev.id)

        return {
            "places_with_loose_ends": open_threads,
            "people_with_more_to_say": unasked,
            "conclusions_you_could_already_draw": len(ripe),
            "clues_found": len(self.state.found),
            "clues_total": len(self.case.clues),
            "narrator_guidance":
                "Render this as the detective taking stock — 'I have not been back to the X' — "
                "never as a checklist. `conclusions_you_could_already_draw` is a count only: "
                "say the evidence on the table may already be enough, never say for what.",
        }

    def hint(self) -> dict:
        """Escalating nudges. Costs are recorded and show up in the grade."""
        self.state.hints_used += 1
        ripe = [
            r for r in self.case.revelations
            if r.id not in self.state.held
            and not any(x not in self.state.held for x in r.requires)
            and sum(1 for c in r.clues if c in self.state.found) >= r.support_needed
        ]
        if ripe:
            rev = ripe[0]
            return {
                "kind": "you_already_know",
                "nudge": rev.nudge or "Re-read what you have. You are one thought from something.",
                "narrator_guidance":
                    "The player has the evidence and hasn't connected it. Deliver the nudge as "
                    "an observation about the *evidence*, not the conclusion. Never name the "
                    "conclusion.",
            }
        f = self.frontier()
        cold = [p for p in f["places_with_loose_ends"] if not p["visited"]]
        return {
            "kind": "go_look",
            "where": (cold or f["places_with_loose_ends"] or [{"place": "your notes"}])[0]["place"],
            "narrator_guidance":
                "Point the detective at a place, not a fact. One sentence of restlessness.",
        }

    # -- endgame -----------------------------------------------------------

    def accuse(self, culprit: str, motive: str = "", method: str = "",
               evidence: list[str] | None = None) -> dict:
        """Name your killer.

        Graded on two axes, because being right by luck is not detection:
        correctness (did you name the right person, motive, method) and support
        (could you have proved it from what you actually hold).
        """
        truth = self.case.truth
        right_person = culprit == truth.culprit
        evidence = [e for e in (evidence or []) if e in self.state.found]

        critical = [r for r in self.case.revelations if r.critical]
        proved = [r.id for r in critical if r.id in self.state.held]
        support = len(proved) / len(critical) if critical else 0.0

        # Did the player hold the clues that actually incriminate?
        incriminating = {
            c.id for c in self.case.clues
            if any(rid in c.supports for rid in (r.id for r in critical))
            and c.reliability != "false"
        }
        held_incriminating = incriminating & set(self.state.found)
        evidential = len(held_incriminating) / len(incriminating) if incriminating else 0.0

        wrong = next((f for f in self.case.false_solutions if f.culprit == culprit), None)

        verdict = {
            "ok": True,
            "correct_culprit": right_person,
            "named": (ch.name if (ch := self.case.character(culprit)) else culprit),
            "solution_chain_proved": f"{len(proved)}/{len(critical)}",
            "support_score": round(support, 2),
            "evidence_score": round(evidential, 2),
            "hints_used": self.state.hints_used,
            "unproved_hunches": [h for h in self.state.hunches if h not in self.state.held],
        }

        if right_person:
            verdict["grade"] = self._grade(support, evidential)
            verdict["truth"] = {
                "culprit": truth.culprit, "motive": truth.motive,
                "method": truth.method, "weapon": truth.weapon,
                "narrative": truth.narrative,
            }
            verdict["motive_matched"] = bool(motive) and self._loose_match(motive, truth.motive)
            verdict["method_matched"] = bool(method) and self._loose_match(method, truth.method)
            verdict["narrator_guidance"] = (
                "Right person. Deliver the full reconstruction from `truth.narrative`. If the "
                "support scores are low, say so honestly — they got there, but the case would "
                "not have held in court. If motive_matched or method_matched is false, walk "
                "through the part they misread."
            )
        else:
            verdict["grade"] = "wrong"
            verdict["what_you_missed"] = (
                [c.id for c in self.case.clues if c.id in incriminating and c.id not in self.state.found]
            )
            if wrong:
                verdict["your_theory_was_anticipated"] = True
                verdict["refuted_by"] = [
                    {"id": cid, "headline": c.headline}
                    for cid in wrong.refuted_by if (c := self.case.clue(cid))
                ]
                verdict["had_refutation"] = [
                    cid for cid in wrong.refuted_by if cid in self.state.found
                ]
                verdict["consequence"] = wrong.consequence
                verdict["narrator_guidance"] = (
                    "Wrong — but this was a reasonable theory the case anticipated. Show the "
                    "clue that breaks it. If `had_refutation` is non-empty, the player was "
                    "holding the refutation and read past it; let that sting land. Then give "
                    "them the choice to keep working rather than ending the case."
                )
            else:
                verdict["narrator_guidance"] = (
                    "Wrong, and not even a theory the case supports. Don't mock. Show one clue "
                    "that flatly contradicts the accusation and let them reconsider."
                )
        self.state.accusations.append({"culprit": culprit, "correct": right_person})
        if right_person:
            self.state.closed = True
        return verdict

    @staticmethod
    def _loose_match(claim: str, actual: str) -> bool:
        """Cheap overlap check; the narrator makes the real call."""
        a = {w for w in claim.lower().split() if len(w) > 3}
        b = {w for w in actual.lower().split() if len(w) > 3}
        return bool(a & b)

    @staticmethod
    def _grade(support: float, evidential: float) -> str:
        score = (support + evidential) / 2
        if score >= 0.95:
            return "airtight"
        if score >= 0.8:
            return "convincing"
        if score >= 0.55:
            return "circumstantial"
        return "lucky guess"

    def journal(self) -> dict:
        return {
            "assist": self.state.assist,
            "location": (l.name if (l := self.case.location(self.state.at)) else "?"),
            "clues": [
                {"id": c.id, "kind": c.kind, "headline": c.headline,
                 "detail": c.detail, "supports_count": len(c.supports)}
                for cid in self.state.found if (c := self.case.clue(cid))
            ],
            "established": [
                {"id": r, "statement": rv.statement}
                for r in self.state.held if (rv := self.case.revelation(r))
            ],
            "suspicions": [
                {"id": h, "statement": rv.statement}
                for h in self.state.hunches
                if h not in self.state.held and (rv := self.case.revelation(h))
            ],
            "progress": f"{len(self.state.found)}/{len(self.case.clues)} clues",
            "narrator_guidance":
                "Present as the detective's notebook. `suspicions` are unproved — render them "
                "in the detective's own hedging voice.",
        }

    def cast_sheet(self) -> dict:
        """Public dossier. Secrets stay sealed until clued."""
        return {
            "cast": [
                {"id": c.id, "name": c.name, "role": c.role, "known": c.public_desc}
                for c in self.case.cast
            ]
        }
