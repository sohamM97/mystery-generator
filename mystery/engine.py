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

# Every notebook operation returns this, and that is the point: writing a line,
# ruling a line out, and replacing a line must all come back sounding the same.
# A narrator who sounds relieved when the player strikes a note has just told
# them the note was wrong.
# Returned for every deduction that isn't accepted, whatever the reason. If
# this string ever forks by reason, the player can tell a theory that missed
# from one that merely lacks evidence, and fishing works again.
HUNCH_GUIDANCE = (
    "Not established. Do NOT say whether it is right, whether it matched anything, or "
    "how close it is — you are not told, and the reasons differ in ways you must not "
    "let show. Have the detective note the idea in their own words and observe that it "
    "would not survive a hostile question yet. Keep the same flat register whether the "
    "thought is inspired or hopeless, and never let the length of your reply vary with "
    "it: a longer answer for a better guess is the same leak."
)

NOTE_GUIDANCE = (
    "Acknowledge in one line and get out of the way. Do NOT react to the content: "
    "never agree, never correct, never let the phrasing warm or cool. A note the "
    "player got right and a note they got wrong must read exactly the same coming "
    "back — this is the `deduce` hunch rule, applied to their own handwriting. That "
    "holds for striking and amending too: never imply the struck line was the wrong "
    "one, or that the new one is better."
)


@dataclass
class State:
    assist: str = "watson"
    at: str = ""  # current location id
    found: list[str] = field(default_factory=list)  # clue ids
    held: list[str] = field(default_factory=list)  # revelation ids
    inferred: list[str] = field(default_factory=list)  # of those, the ones the assist drew
    hunches: list[str] = field(default_factory=list)  # believed but unevidenced
    # The player-facing record of unproved ideas, in their own words, whether
    # or not the statement matched anything. `hunches` above is the private
    # tally for the endgame; this is the only version anyone gets to read.
    hypotheses: list[dict] = field(default_factory=list)
    visited: list[str] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)  # source keys already used
    turns: int = 0
    turns_since_progress: int = 0
    hints_used: int = 0
    accusations: list[dict] = field(default_factory=list)
    closed: bool = False
    notes: list[dict] = field(default_factory=list)  # the player's own words

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

        Everything drawn here is recorded in `state.inferred`, because a
        conclusion the game handed you and a conclusion you fought for are not
        the same thing and must never be displayed as though they were. Without
        that mark, `board` reads back the game's own reasoning in the player's
        voice, and a player at lestrade is looking at a walkthrough that claims
        to be their notes.
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
                    self.state.inferred.append(rev.id)
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
        """Look at a named thing where the detective is standing.

        Three outcomes, and the engine used to collapse the first two:

        - the thing is here → whatever it has to give, or nothing
        - the thing is *named in this room's description* but its clue lives in
          a room next door — the tray outside room four, visible from inside it
          and only examinable from the landing. The old code returned "nothing
          here", which reads as an empty tray rather than a tray out of reach,
          and a narrator relaying that states a fact about the world that the
          engine never said.
        - nothing of that name here at all → say so as a failed search, never
          as a finding

        Refs are matched loosely, because the case calls it `tray` and the room
        description calls it a `supper tray`, and a player should not have to
        guess the author's noun.
        """
        loc = self.case.location(self.state.at)
        target = self._resolve_ref(ref, self._examinables_at(self.state.at))
        if target:
            return self._collect(f"examine:{self.state.at}:{target}".lower(),
                                 f"You examine the {ref}.")

        # Only chase a thing into the next room when *this* room's description
        # already named it. Otherwise "is there a bloodstained knife?" becomes a
        # way to ask the engine what exists nearby.
        if loc and self._mentioned_in(ref, loc.desc):
            for other in loc.connects:
                if other not in self.reachable_locations():
                    continue
                if self._resolve_ref(ref, self._examinables_at(other)):
                    there = self.case.location(other)
                    return self._examine_miss(
                        ref,
                        at_hand_elsewhere=there.name if there else "",
                        guidance=(
                            "The thing is real and this room's own description mentions it, but "
                            "it is not where the detective is standing — it is in "
                            f"{there.name if there else 'another room'}. Say that plainly, in "
                            "one line, as a matter of where their feet are. Do NOT describe the "
                            "thing, do not say whether it holds anything, and do not imply it "
                            "is worth the walk."),
                    )
            return self._examine_miss(
                ref, guidance="Nothing to find. Say so in one line and don't pad it.")

        return self._examine_miss(
            ref, unknown=True,
            guidance=("There is nothing of that name where the detective is standing. Say so "
                      "as a failed search — they look and it isn't here — never as a finding "
                      "about the thing itself, which the engine has told you nothing about. "
                      "Name no alternative and point nowhere."))

    def _examine_miss(self, ref: str, guidance: str, unknown: bool = False,
                      at_hand_elsewhere: str = "") -> dict:
        """A look that found nothing, shaped like `_collect` so callers don't fork."""
        out = {
            "ok": True,
            "flavour": f"You examine the {ref}.",
            "speaker": "",
            "new_clues": [],
            "already_known": [],
            "nothing_here": True,
            "inferences": [],
            "narrator_guidance": guidance,
        }
        if unknown:
            out["unknown_target"] = True
        if at_hand_elsewhere:
            out["at_hand_elsewhere"] = at_hand_elsewhere
        return out

    def _examinables_at(self, loc_id: str) -> set[str]:
        """Every examinable ref in a location, gated ones included.

        Gated clues stay in the set on purpose: a gated object must still route
        into `_collect`, which has the guidance for describing a place as
        ordinary. Dropping it here would make it report as absent instead.
        """
        return {c.source.ref for c in self.case.clues
                if c.source.kind == "examine" and c.source.at == loc_id}

    @staticmethod
    def _normalise(s: str) -> str:
        return " ".join(w.strip(".,;:'\"!?") for w in s.lower().split())

    @classmethod
    def _resolve_ref(cls, ref: str, candidates: set[str]) -> str:
        """Match the player's noun to the author's. Exact, then containment."""
        want = cls._normalise(ref)
        if not want:
            return ""
        by_norm = {cls._normalise(c): c for c in candidates}
        if want in by_norm:
            return by_norm[want]
        near = [orig for norm, orig in by_norm.items()
                if want in norm or norm in want]
        return near[0] if len(near) == 1 else ""

    @classmethod
    def _mentioned_in(cls, ref: str, text: str) -> bool:
        """Does the room's own description name this thing?"""
        want = cls._normalise(ref)
        return bool(want) and want in cls._normalise(text)

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

    def deduce(self, rid: str, evidence: list[str] | None = None,
               as_stated: str = "") -> dict:
        """The player states a conclusion. The engine rules on whether they've
        earned it.

        Obra Dinn's lesson: confirm, but don't make confirmation cheap. You can
        be right without grounds — the engine records that as a hunch, and the
        final grade counts it separately from a proved conclusion.

        `rid` may be empty: the narrator matches the player's sentence against
        the case's conclusions and often there is nothing to match. That is a
        normal move, not an error, and it must be recorded like any other
        unproved statement — see `_record_hypothesis`.

        `as_stated` is the player's own sentence, and it is what gets filed and
        read back. Never substitute the case's wording for a matched statement:
        the player would see their own phrasing for the theories that missed
        and the author's for the ones that landed, which gives the whole thing
        away in a single glance at the notebook.
        """
        rev = self.case.revelation(rid) if rid else None
        if rid and not rev:
            return {"ok": False, "error": f"no such conclusion: {rid}"}
        if rev and rev.id in self.state.held:
            return {"ok": True, "already": True, "statement": rev.statement}

        # Everything that isn't an acceptance leaves by the same door, carrying
        # the same fields and the same guidance: a statement with no matching
        # conclusion, a true one resting on an unestablished step, and a true
        # one short of evidence are indistinguishable from outside. They were
        # not, until now — only a *true* statement could match an id, so
        # appearing in `suspicions` at all told the player they were right, and
        # `have`/`need` was a progress bar towards a conclusion that existed
        # only if their theory held. Both are gone.
        if rev is None:
            return self._record_hypothesis(as_stated, None)

        missing_prereq = [r for r in rev.requires if r not in self.state.held]
        if missing_prereq:
            return self._record_hypothesis(as_stated, rev.id)

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

        return self._record_hypothesis(as_stated, rev.id)

    def _record_hypothesis(self, as_stated: str, rid: str | None) -> dict:
        """File an unproved statement in the player's own words.

        `rid` is kept in state for the endgame tally and never leaves this
        method — the return value is byte-identical whether it is None or not.
        """
        if rid and rid not in self.state.hunches:
            self.state.hunches.append(rid)
        text = as_stated.strip()
        if text and not any(h["text"] == text for h in self.state.hypotheses):
            self.state.hypotheses.append({
                "text": text,
                "turn": self.state.turns,
                "at": (l.name if (l := self.case.location(self.state.at)) else "?"),
            })
        return {
            "ok": True,
            "accepted": False,
            "recorded": True,
            "narrator_guidance": HUNCH_GUIDANCE,
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
            verdict["motive_overlap"] = self._loose_match(motive, truth.motive)
            verdict["method_overlap"] = self._loose_match(method, truth.method)
            verdict["narrator_guidance"] = (
                "Right person. Deliver the full reconstruction from `truth.narrative`. "
                "`motive_overlap` and `method_overlap` are crude word-overlap ratios, not "
                "rulings: you have both the player's words and `truth`, so read them yourself "
                "and make the call. A low overlap on a motive said in different words is not a "
                "miss, and a high one on a coincidental word is not a hit. If the "
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

    # Words that two unrelated sentences about the same case will share anyway,
    # and so carry no evidence that the player understood the motive.
    _STOPWORDS = frozenset("""
        that this then than they them their there were was been have that with
        into onto from about because while when what which would could should
        after before over under between during against
    """.split())

    @classmethod
    def _loose_match(cls, claim: str, actual: str) -> float:
        """How much of the true statement the player's wording covers, 0–1.

        A ratio rather than a boolean, and reported as `*_overlap` rather than
        `*_matched`, because it is not a ruling: the same motive said in the
        player's own words scores low, and one shared coincidental noun used to
        score a full match. The narrator holds both texts and decides.
        """
        def words(s: str) -> set[str]:
            return {w.strip(".,;:'\"!?") for w in s.lower().split()
                    if len(w) > 3} - cls._STOPWORDS
        a, b = words(claim), words(actual)
        if not a or not b:
            return 0.0
        return round(len(a & b) / len(b), 2)

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

    # -- the player's own notebook -----------------------------------------

    def note(self, text: str) -> dict:
        """Write a line in the player's own hand.

        Notes are the one thing in the journal the engine does not vouch for.
        The player may well write down something a character lied to them
        about, and must be able to — a notebook you can only fill with true
        statements is a notebook that solves the case for you. So: stored
        verbatim, stamped with where and when, never checked against the seal.
        """
        entry = {
            "text": text,
            "turn": self.state.turns,
            "at": (l.name if (l := self.case.location(self.state.at)) else "?"),
        }
        self.state.notes.append(entry)
        return {
            "ok": True,
            "note": self._note_view(len(self.state.notes) - 1),
            "count": len(self._notes_view()),
            "narrator_guidance": NOTE_GUIDANCE,
        }

    # Notes are numbered for the player 1-based, and the numbering never
    # shifts: a struck line keeps its number and its place, so "strike 3"
    # means the same thing in turn forty as it did in turn four.
    def _note_view(self, i: int) -> dict:
        entry = {k: v for k, v in self.state.notes[i].items() if k != "revisions"}
        return {"n": i + 1, **entry}

    def _note_index(self, n: int) -> int | None:
        """Resolve a player-facing note number to a list index.

        Torn-out lines keep their slot in state but stop being addressable, so
        a stale number can never land on a line the player has removed.
        """
        if not isinstance(n, int) or n < 1 or n > len(self.state.notes):
            return None
        if self.state.notes[n - 1].get("torn"):
            return None
        return n - 1

    def _no_such_note(self, n: int) -> dict:
        return {
            "ok": False,
            "error": f"there is no note {n}",
            "count": len(self._notes_view()),
            "narrator_guidance":
                "The detective looks for that line and doesn't find it. Say so in one "
                "flat sentence and offer to read the notebook back. Pass no judgement.",
        }

    def strike(self, n: int) -> dict:
        """Rule a line through a note without taking it off the page.

        The player will write down things that turn out to be wrong — a lie
        they were told, a number they misread — and they must be able to
        retract them. Struck, not erased: still legible, still numbered,
        visibly crossed out, and `unstrike` puts it back.
        """
        i = self._note_index(n)
        if i is None:
            return self._no_such_note(n)
        already = bool(self.state.notes[i].get("struck"))
        self.state.notes[i]["struck"] = True
        self.state.notes[i].setdefault("struck_turn", self.state.turns)
        return {
            "ok": True,
            "already_struck": already,
            "note": self._note_view(i),
            "count": len(self._notes_view()),
            "narrator_guidance": NOTE_GUIDANCE,
        }

    def unstrike(self, n: int) -> dict:
        """Take the line back off a struck note.

        The player changes their mind about changing their mind — usually
        because the thing they crossed out turned out to be right after all.
        Nothing about the strike is worth preserving once they've reversed it,
        so this leaves no scar.
        """
        i = self._note_index(n)
        if i is None:
            return self._no_such_note(n)
        was = bool(self.state.notes[i].pop("struck", False))
        self.state.notes[i].pop("struck_turn", None)
        return {
            "ok": True,
            "was_struck": was,
            "note": self._note_view(i),
            "count": len(self._notes_view()),
            "narrator_guidance": NOTE_GUIDANCE,
        }

    def rewrite(self, n: int, text: str) -> dict:
        """Replace a note's wording in place, keeping its number and its slot.

        `amend` is for changing your mind; this is for fixing how a line was
        written down — a misheard figure, a sentence that came out wrong. The
        superseded wording is kept in `revisions` rather than shown, so the
        page reads clean while the record of what the player first wrote is
        still there in state for anyone who goes looking.
        """
        i = self._note_index(n)
        if i is None:
            return self._no_such_note(n)
        entry = self.state.notes[i]
        entry.setdefault("revisions", []).append(
            {"text": entry["text"], "turn": entry.get("turn"), "until": self.state.turns}
        )
        entry["text"] = text
        entry["revised_turn"] = self.state.turns
        return {
            "ok": True,
            "note": self._note_view(i),
            "count": len(self._notes_view()),
            "narrator_guidance": NOTE_GUIDANCE,
        }

    def tear_out(self, n: int) -> dict:
        """Take a line off the page entirely.

        The blunt instrument, and the last resort: `strike` is the honest way
        to retract something, because the fact that the player once believed it
        is part of their reasoning. This is for lines that were never reasoning
        at all — a duplicate, a typo, a note written against the wrong case.
        The text survives in state as a tombstone; it just stops being part of
        the notebook, and its number is never reused.
        """
        i = self._note_index(n)
        if i is None:
            return self._no_such_note(n)
        self.state.notes[i]["torn"] = True
        self.state.notes[i]["torn_turn"] = self.state.turns
        return {
            "ok": True,
            "note": {"n": n, **self.state.notes[i]},
            "count": len(self._notes_view()),
            "narrator_guidance": NOTE_GUIDANCE,
        }

    def amend(self, n: int, text: str) -> dict:
        """Strike a note and write its replacement underneath.

        Two lines, not one edited line: the old wording stays crossed out where
        it was, and the new one is a fresh entry stamped with where and when
        the player actually changed their mind.
        """
        struck = self.strike(n)
        if not struck["ok"]:
            return struck
        i = self._note_index(n)
        entry = {
            "text": text,
            "turn": self.state.turns,
            "at": (l.name if (l := self.case.location(self.state.at)) else "?"),
            "replaces": n,
        }
        self.state.notes.append(entry)
        return {
            "ok": True,
            "note": self._note_view(len(self.state.notes) - 1),
            "struck": self._note_view(i),
            "count": len(self._notes_view()),
            "narrator_guidance": NOTE_GUIDANCE,
        }

    def notebook(self) -> dict:
        return {
            "notes": self._notes_view(),
            "count": len(self._notes_view()),
            "narrator_guidance":
                "Read back verbatim as the detective's own margin notes, in the order written, "
                "with their numbers — the player needs the numbers to strike or amend a line. "
                "Never annotate them, never reorder them by how right they are, and never "
                "quietly drop one that turned out to be wrong. A note with `struck: true` is "
                "crossed out but still on the page: render it struck through, in its place, "
                "and never omit it. A note with `replaces` is the line the player wrote "
                "instead — say so flatly, without suggesting the new one is any better.",
        }

    def _notes_view(self) -> list[dict]:
        return [
            self._note_view(i) for i in range(len(self.state.notes))
            if not self.state.notes[i].get("torn")
        ]

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
                {"id": r, "statement": rv.statement, "drawn_by": self._drawn_by(r)}
                for r in self.state.held if (rv := self.case.revelation(r))
            ],
            "suspicions": self._suspicions_view(),
            "notes": self._notes_view(),
            "progress": f"{len(self.state.found)}/{len(self.case.clues)} clues",
            "narrator_guidance":
                "Present as the detective's notebook. `suspicions` are the player's own "
                "unproved statements, in their own words — matched and unmatched alike, and "
                "you are not told which is which. Render them in the detective's hedging "
                "voice, all in the same register. An `established` entry with "
                "`drawn_by: 'the game'` was inferred for the player by the assist level, not "
                "reasoned out by them: never read it back as though they thought of it. "
                "`notes` are the player's own words: "
                "quote them back untouched and pass no judgement on them. Ones marked "
                "`struck` are crossed out but still on the page — render them struck "
                "through, never omit them.",
        }

    def _suspicions_view(self) -> list[dict]:
        """The player's unproved statements, in their own words.

        Deliberately carries no id and no match flag. Everything the player
        said and did not prove sits here on equal terms; nothing in the shape
        of an entry betrays whether the case has a conclusion behind it.
        """
        return [dict(h) for h in self.state.hypotheses]

    def _drawn_by(self, rid: str) -> str:
        """Who reached this conclusion — the player, or the assist level."""
        return "the game" if rid in self.state.inferred else "you"

    def board(self) -> dict:
        """The case board: what the player has concluded, and what proved it.

        `journal` lists conclusions as bare statements, which makes a long case
        feel like a pile of sentences the game handed you. This shows the
        chain — clue, clue, therefore — so the player can see their own
        reasoning standing up, and spot the conclusion resting on one thread.

        It shows only what they already hold. Nothing here is forward-looking:
        the moment a board says 'you are close to X' it has started solving the
        case, and `frontier` (shape, never content) is the surface for that.

        Assist decides how much of the wiring is drawn:
          holmes    the conclusions, nothing else. You remember why.
          watson    the clues under each conclusion, and what it opened.
          lestrade  the above, plus which conclusions rest on the bare minimum.
        """
        assist = self.state.assist
        chain = []
        for rid in self.state.held:
            rev = self.case.revelation(rid)
            if not rev:
                continue
            entry: dict = {
                "id": rid,
                "statement": rev.statement,
                "drawn_by": self._drawn_by(rid),
            }
            if assist != "holmes":
                entry["because"] = [
                    {"id": c.id, "headline": c.headline}
                    for cid in rev.clues if cid in self.state.found
                    and (c := self.case.clue(cid))
                ]
                entry["opened"] = [
                    l.name for l in self.case.locations if rid in l.gates
                ]
            if assist == "lestrade":
                held = sum(1 for c in rev.clues if c in self.state.found)
                entry["resting_on_minimum"] = held <= rev.support_needed
            chain.append(entry)

        supporting = {
            cid for rid in self.state.held
            if (rev := self.case.revelation(rid))
            for cid in rev.clues if cid in self.state.found
        }
        loose = [
            {"id": c.id, "headline": c.headline}
            for cid in self.state.found
            if cid not in supporting and (c := self.case.clue(cid))
        ]

        out = {
            "assist": assist,
            "established": chain,
            "unattached_clues": loose,
            "progress": f"{len(self.state.held)} conclusions, "
                        f"{len(self.state.found)}/{len(self.case.clues)} clues",
            "narrator_guidance":
                "Render as the detective laying it out — conclusions with the evidence under "
                "them, in their own words. `drawn_by` is not decoration: conclusions marked "
                "'you' are the player's own, and conclusions marked 'the game' were handed to "
                "them by the assist level. Keep the two visibly apart — a player reading their "
                "board must never mistake the game's reasoning for their own. Do not apologise "
                "for the handed ones or praise the earned ones; just don't merge them. "
                "`unattached_clues` are things they hold that no "
                "conclusion of theirs uses yet: list them flatly as loose ends and never say "
                "or hint at what they might prove. Nothing here looks forward; do not add a "
                "'so the next step is' of your own.",
        }
        # Suspicions are shown at every assist level, including holmes: they
        # are nothing but the player's own unproved sentences, so there is
        # nothing here to be handed and nothing to fish for.
        out["suspicions"] = self._suspicions_view()
        out["narrator_guidance"] += (
            " `suspicions` are the player's own unproved statements in their own words. "
            "Render them with no more confidence than the day they were first said out loud, "
            "and give every one of them the same weight — you are not told which of them the "
            "case can back."
        )
        return out

    def cast_sheet(self) -> dict:
        """Public dossier. Secrets stay sealed until clued."""
        return {
            "cast": [
                {"id": c.id, "name": c.name, "role": c.role, "known": c.public_desc}
                for c in self.case.cast
            ]
        }
