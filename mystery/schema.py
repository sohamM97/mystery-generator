"""Case file schema.

A case is authored once, validated, then sealed. After sealing the truth is
immutable: the narrator never recalls it from memory, it queries for it.

Vocabulary
----------
clue        An atomic, discoverable fact. Has a *source* (where you get it) and
            a set of *gates* (what you must already understand to get it).
revelation  A conclusion the detective can reach. Supported by clues, may
            require other revelations first. Forms a DAG.
lead        Implicit: a clue whose gates are satisfied but which is unfound.
truth       The answer key. Culprit, method, motive, and the narrative.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any

SCHEMA_VERSION = 1

CLUE_KINDS = {"physical", "testimony", "document", "observation", "absence"}
RELIABILITY = {"hard", "soft", "false"}
ASSIST_LEVELS = ("holmes", "watson", "lestrade")


def _req(d: dict, key: str, ctx: str) -> Any:
    if key not in d:
        raise ValueError(f"{ctx}: missing required field {key!r}")
    return d[key]


@dataclass
class Character:
    id: str
    name: str
    role: str
    public_desc: str
    # Both optional, both free text, both shown in the casebook when the author
    # filled them in. Age is a string because authors write "forty-one" and
    # "in her fifties" and a number cannot hold the second one. Gender is the
    # author's own word: the engine never infers one from a name, and a
    # character the author left blank is displayed without the field rather
    # than with a guess.
    age: str = ""
    gender: str = ""
    # Act index in which this character first appears on the page. Knox #1
    # requires the culprit to show up early, so the validator reads this.
    introduced_at: int = 0
    secrets: list[str] = field(default_factory=list)
    # Topics this character will not discuss until a revelation is held.
    locked_topics: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def from_dict(d: dict) -> "Character":
        return Character(
            id=_req(d, "id", "character"),
            name=_req(d, "name", "character"),
            role=d.get("role", ""),
            public_desc=d.get("public_desc", ""),
            age=str(d.get("age", "")).strip(),
            gender=str(d.get("gender", "")).strip(),
            introduced_at=int(d.get("introduced_at", 0)),
            secrets=list(d.get("secrets", [])),
            locked_topics=dict(d.get("locked_topics", {})),
        )


@dataclass
class Location:
    id: str
    name: str
    desc: str
    connects: list[str] = field(default_factory=list)
    # Locations the player cannot reach until they know something.
    gates: list[str] = field(default_factory=list)

    @staticmethod
    def from_dict(d: dict) -> "Location":
        return Location(
            id=_req(d, "id", "location"),
            name=_req(d, "name", "location"),
            desc=d.get("desc", ""),
            connects=list(d.get("connects", [])),
            gates=list(d.get("gates", [])),
        )


@dataclass
class Source:
    """Where a clue is obtained."""

    kind: str  # "examine" | "ask" | "search" | "event"
    at: str = ""  # location id
    ref: str = ""  # object name or character id
    topic: str = ""  # for "ask"

    @staticmethod
    def from_dict(d: dict) -> "Source":
        return Source(
            kind=_req(d, "kind", "source"),
            at=d.get("at", ""),
            ref=d.get("ref", ""),
            topic=d.get("topic", ""),
        )

    def key(self) -> str:
        if self.kind == "ask":
            return f"ask:{self.ref}:{self.topic}".lower()
        if self.kind == "examine":
            return f"examine:{self.at}:{self.ref}".lower()
        if self.kind == "search":
            return f"search:{self.at}".lower()
        return f"event:{self.ref}".lower()


@dataclass
class Clue:
    id: str
    kind: str
    headline: str  # one line, goes in the journal
    detail: str  # what the narrator describes
    source: Source
    gates: list[str] = field(default_factory=list)  # revelation ids
    supports: list[str] = field(default_factory=list)  # revelation ids
    reliability: str = "hard"
    # For reliability == "false": the clue is a lie or a misreading. The
    # narrator must deliver it straight, and must keep delivering it the same
    # way. This field records what actually undoes it.
    debunked_by: list[str] = field(default_factory=list)
    # Never shown to the player. Notes to keep the narrator consistent.
    hidden_note: str = ""

    @staticmethod
    def from_dict(d: dict) -> "Clue":
        return Clue(
            id=_req(d, "id", "clue"),
            kind=_req(d, "kind", "clue"),
            headline=_req(d, "headline", "clue"),
            detail=d.get("detail", ""),
            source=Source.from_dict(_req(d, "source", f"clue {d.get('id')}")),
            gates=list(d.get("gates", [])),
            supports=list(d.get("supports", [])),
            reliability=d.get("reliability", "hard"),
            debunked_by=list(d.get("debunked_by", [])),
            hidden_note=d.get("hidden_note", ""),
        )


@dataclass
class Revelation:
    id: str
    statement: str  # "Marlowe was not in the study at 9pm"
    requires: list[str] = field(default_factory=list)  # revelation ids
    clues: list[str] = field(default_factory=list)
    support_needed: int = 2  # clues required before the engine accepts it
    critical: bool = False  # part of the solution chain
    # Shown when the player is stuck; a nudge, not the answer.
    nudge: str = ""

    @staticmethod
    def from_dict(d: dict) -> "Revelation":
        clues = list(d.get("clues", []))
        return Revelation(
            id=_req(d, "id", "revelation"),
            statement=_req(d, "statement", "revelation"),
            requires=list(d.get("requires", [])),
            clues=clues,
            support_needed=int(d.get("support_needed", min(2, len(clues)) or 1)),
            critical=bool(d.get("critical", False)),
            nudge=d.get("nudge", ""),
        )


@dataclass
class TimelineEvent:
    t: int  # minutes past midnight
    actor: str  # character id
    location: str
    action: str
    witnesses: list[str] = field(default_factory=list)
    trace: str = ""  # clue id this event leaves behind

    @staticmethod
    def from_dict(d: dict) -> "TimelineEvent":
        return TimelineEvent(
            t=int(_req(d, "t", "timeline event")),
            actor=_req(d, "actor", "timeline event"),
            location=_req(d, "location", "timeline event"),
            action=_req(d, "action", "timeline event"),
            witnesses=list(d.get("witnesses", [])),
            trace=d.get("trace", ""),
        )


@dataclass
class FalseSolution:
    """A wrong answer the case must genuinely support.

    Sherlock: Crimes & Punishments ships 3-5 solutions per case and lets you
    convict the wrong person. That only works if the wrong answer is honestly
    reachable *and* honestly refutable.
    """

    id: str
    culprit: str
    pitch: str  # the case against them, as a reasonable detective would build it
    refuted_by: list[str] = field(default_factory=list)  # clue ids
    consequence: str = ""  # what happens if the player convicts them

    @staticmethod
    def from_dict(d: dict) -> "FalseSolution":
        return FalseSolution(
            id=_req(d, "id", "false solution"),
            culprit=_req(d, "culprit", "false solution"),
            pitch=d.get("pitch", ""),
            refuted_by=list(d.get("refuted_by", [])),
            consequence=d.get("consequence", ""),
        )


@dataclass
class Truth:
    culprit: str
    method: str
    motive: str
    weapon: str = ""
    time: int = 0
    accomplices: list[str] = field(default_factory=list)
    narrative: str = ""  # the full account, revealed only at the end

    @staticmethod
    def from_dict(d: dict) -> "Truth":
        return Truth(
            culprit=_req(d, "culprit", "truth"),
            method=_req(d, "method", "truth"),
            motive=_req(d, "motive", "truth"),
            weapon=d.get("weapon", ""),
            time=int(d.get("time", 0)),
            accomplices=list(d.get("accomplices", [])),
            narrative=d.get("narrative", ""),
        )


@dataclass
class Case:
    meta: dict
    cast: list[Character]
    locations: list[Location]
    clues: list[Clue]
    revelations: list[Revelation]
    timeline: list[TimelineEvent]
    truth: Truth
    false_solutions: list[FalseSolution] = field(default_factory=list)
    # Declared genre allowances. Knox forbids secret passages and twins unless
    # you own up to them; declaring one here makes the validator demand clues.
    conceits: list[str] = field(default_factory=list)
    opening: str = ""

    @staticmethod
    def from_dict(d: dict) -> "Case":
        return Case(
            meta=dict(d.get("meta", {})),
            cast=[Character.from_dict(x) for x in _req(d, "cast", "case")],
            locations=[Location.from_dict(x) for x in _req(d, "locations", "case")],
            clues=[Clue.from_dict(x) for x in _req(d, "clues", "case")],
            revelations=[Revelation.from_dict(x) for x in _req(d, "revelations", "case")],
            timeline=[TimelineEvent.from_dict(x) for x in d.get("timeline", [])],
            truth=Truth.from_dict(_req(d, "truth", "case")),
            false_solutions=[FalseSolution.from_dict(x) for x in d.get("false_solutions", [])],
            conceits=list(d.get("conceits", [])),
            opening=d.get("opening", ""),
        )

    @staticmethod
    def load(path: str) -> "Case":
        with open(path, "r", encoding="utf-8") as fh:
            return Case.from_dict(json.load(fh))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["meta"] = {**self.meta, "schema_version": SCHEMA_VERSION}
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    # -- lookups -----------------------------------------------------------
    def character(self, cid: str) -> Character | None:
        return next((c for c in self.cast if c.id == cid), None)

    def location(self, lid: str) -> Location | None:
        return next((l for l in self.locations if l.id == lid), None)

    def clue(self, cid: str) -> Clue | None:
        return next((c for c in self.clues if c.id == cid), None)

    def revelation(self, rid: str) -> Revelation | None:
        return next((r for r in self.revelations if r.id == rid), None)

    def clues_from(self, source_key: str) -> list[Clue]:
        return [c for c in self.clues if c.source.key() == source_key]
