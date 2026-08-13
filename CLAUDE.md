# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Greeting the user

Someone opening Claude Code here is either a **player** who wants a mystery or a
**developer** who wants to work on the engine, and you cannot tell which from an
empty prompt. So when a session opens with a bare greeting or an unscoped
"what can you do" — not when they arrive with an actual task — open with a short
greeting in the register of the genre (a line or two, atmospheric, never twee
and never a whole scene), then say plainly what's on offer:

- **Play** — `/new-case [premise]` to author and seal a fresh mystery,
  `/play` to run one. Mention any case already sitting in `cases/` and whether
  it has been started (`state.json` → `turns`).
- **Build** — work on the engine, validator, seal, or the two skills.

If they lean towards playing, tell them about the difficulty dial before they
commit, because it is the point of the project and it is not discoverable:

- `holmes` — nothing is ever inferred for you. Every connection is yours.
- `watson` — **default.** Routine steps resolve themselves; every conclusion
  that matters is still yours.
- `lestrade` — the game voices each deduction the evidence supports and you
  follow the thread.

Set it at authoring time (`seal --assist <level>`) and say it can be changed
mid-case (`assist --case cases/<slug> <level>`) — offer the change if they're
bouncing off a case or finding it too easy. Note that this is separate from a
case's own `meta.difficulty`, which is fixed when the case is authored and
cannot be changed afterwards.

Tell them what else is on the table, because none of it is discoverable and all
of it is free. Three things, not a catalogue — see "Name three things to the
player, never six" below:

- Taking stock at any point: what they have concluded and what proved it, and
  which threads they have not pulled.
- Their own notebook, which they can write in, strike and amend.
- A `hint`, which is recorded and read out with the final verdict. They should
  hear that price *before* they spend one, not after.

If they would rather read their records than ask for them, `/casebook` lays all
of it out on pages — ←/→ between pages, `q` to close, in a terminal of their
own. Save that for when they ask; it does not belong in the opening.

Then ask which they want. Don't pick for them, and don't start narrating or
authoring before they've said.

## Commands

```bash
python3 tests/test_playthrough.py                  # the whole test suite; no pytest, no deps
python3 -m mystery.cli validate drafts/<slug>.case.json
python3 -m mystery.cli seal drafts/<slug>.case.json --assist watson --delete-draft
python3 -m mystery.cli <look|go|examine|search|ask|deduce|accuse|...> --case cases/<slug>
```

Python 3.10+, standard library only. There is no lint config and no package
manifest — don't add dependencies without being asked; "works from a cold clone"
is a design property here, not an accident.

The test suite is a single script of hand-rolled `check(label, condition)`
assertions that plays `examples/ashgrove.case.json` end to end. There is no
per-test selection flag; to run one section, edit `main()` in
`tests/test_playthrough.py`.

### Never point `--case` at `cases/` while working on the engine

Anything under `cases/` may be a case somebody is part-way through. `deduce`,
`note`, `go`, `hint` and the rest write to `cases/<slug>/state.json`, and the
engine cannot tell a development session from a played turn — both look like
one CLI call. Testing a change against a live case is how `cases/pierhead`
ended up holding a suspicion in a player's name that the player never said:

```bash
# don't — this writes a turn into someone's game
python3 -m mystery.cli deduce --case cases/pierhead --as-stated "..."

# do — a throwaway copy: same sealed case, same key, its own state
python3 -m mystery.cli scratch --case cases/pierhead   # -> scratch/pierhead-1
python3 -m mystery.cli deduce --case scratch/pierhead-1 --as-stated "..."
```

`scratch/` is gitignored. Delete a copy when you are done with it, or leave it.

Every command that writes state first appends the state it replaced to
`cases/<slug>/state.history.jsonl`, along with the argv that caused the write —
which is what makes "who wrote this line" answerable at all. `undo --case <dir>`
restores the last of those and reports which command it took back. Repeat it to
walk further back.

`scratch` and `undo` are both left out of `--help`, and neither appears in the
play skill. Everything a narrator can see it will eventually offer the player,
and a player who can undo a turn can take back a spent hint or a failed
accusation — at which point `hints_used` and the accusation record stop meaning
anything in the final grade. They are repair tools for whoever owns the repo.

## Architecture

The repo exists to solve one failure mode: **an LLM asked to hold a mystery in
its head over fifty turns will quietly revise the culprit to match whatever the
player is theorising.** Every structural decision follows from refusing that.

**The truth is sealed, and the narrator queries it rather than remembering it.**
`mystery/seal.py` encrypts the authored case into `cases/<slug>/case.sealed`
(HMAC-SHA256 counter mode, encrypt-then-MAC, stdlib only). The narrator reaches
it *only* through `mystery/cli.py`, one scoped call per turn, and renders the
JSON it gets back. If you are ever about to write a case fact from memory, that
is the bug this architecture exists to prevent.

**Two LLM roles, two skills, and they must not bleed.** `.claude/skills/new-case`
is the author: it writes the whole truth, validates, seals, and *stops* —
it never narrates. `.claude/skills/play` is the narrator: it never knows the
solution. Changes to either should preserve that separation.

**The engine is the source of every fact; the narrator supplies only voice.**
`mystery/engine.py` holds play state (`State` → `cases/<slug>/state.json`) and
gates content on *knowledge*, not objects: clues and locations carry
`gates: [revelation_id]`, so a door opens because the player understood
something. Every engine response carries a `narrator_guidance` string written
for the LLM and never shown to the player, and clue payloads carry a
`NEVER_REVEAL` block (reliability + author's note) whose whole purpose is to
keep a lying character lying *consistently* in turn forty.

**Deduction cannot be fished.** `Engine.deduce` accepts a conclusion only when
the player already holds enough supporting clues; otherwise it records a
*hunch* and returns without saying whether the hunch was right. Preserving that
silence is the one behaviour the whole game rests on — a narrator that leaks
warm/cold here turns detection into guessing, and the case is over. `accuse` then grades on two
independent axes, correctness and provability, which is why `lucky guess` is a
real outcome alongside `airtight`.

**There is no clock, and the endgame counts only what the player leaned on.**
`state.turns` advances so that notes and suspicions carry a chronology, and
nothing reads it — no deadline, no scoring, no escalation. So the narrator must
never warn a player that an action costs them something: looking, going, asking
and searching are all free, and a player who thinks their wandering is being
tallied investigates more timidly than the design wants. Two references settled
this. The Séance of Blake Manor stops its clock for travel and for thinking,
charging only for investigative choices; Danganronpa scores a trial on wrong
assertions and never times the investigation at all.

What `accuse` reports instead is `how_you_got_here`: the assist level and how
many conclusions it drew, hints spent, earlier accusations, conclusions voiced
and never carried, and clues held that nothing rests on. Counts, read out flat.
It is not a second grade — `lestrade` handing over four conclusions is what
`lestrade` is for — and it exists so the difficulty dial is visible at the end
rather than free.

**Assist levels are `auto_infer`'s only job.** `holmes` infers nothing,
`watson` (default) auto-resolves non-critical revelations so the player spends
attention only on conclusions that matter, `lestrade` resolves everything the
evidence supports.

**Nothing is playable until it is proven fair.** `mystery/validate.py` encodes
Knox, Van Dine and the Three Clue Rule as machine checks, and `simulate()`
plays the case as a perfect detective to prove every critical conclusion is
reachable. `seal` refuses to seal a case with errors unless `--force`. Expect a
freshly authored case to fail validation the first time — that is the tool
working. `docs/DESIGN.md` maps each check back to the craft source it came from
and is the right place to look before changing validation rules.

`mystery/schema.py` is the vocabulary for all of the above; `docs/CASE_SCHEMA.md`
is its prose companion.

## How to write here

Applies to prose in chat, docs, code comments and commit messages alike. An
explanation that only makes sense to someone who already understands it has
explained nothing.

**Words not to use.** Borrowed metaphor that names your opinion of a thing
instead of the thing:

| banned | say what actually happens |
|---|---|
| plumbing | non-critical conclusions, the connecting steps, bookkeeping |
| load-bearing | why it matters: "the game dissolves if this leaks" |
| pre-flight | check it before asking |
| hydrate | fill in, load the values into |
| bake in | fixed when the case is authored, hard-coded |
| out of the box | with no configuration, from a cold clone |
| bites us | if this is wrong, X breaks — name X |
| spike | a small throwaway script that checks one thing |
| guard | the check that stops X — name what it stops |

Same for idioms and phrasal verbs where a plain verb exists. A boiler or a pipe
*in a case* is a boiler and a pipe, and a case's `gates` are gates — the ban is
on the metaphor, never on this project's own nouns. `surface` stays too:
`open-questions` is a spoiler surface. Add future entries here.

**Keep the real name of a thing, and explain it the first time.** `revelation`,
`gate`, `assist level`, `critical`, `seal`, `hunch` are this project's
vocabulary and what someone will grep for. Write the name and what it does in
one breath — "a revelation — a conclusion the case will accept once you hold
enough clues for it" — then just use the word. Do not paraphrase a real term
into everyday words: it is longer, vaguer, and unsearchable. (`surface` as a
noun is ours too — `open-questions` is a spoiler surface — and stays.)

**Explain why something matters with a concrete example, not an abstract
description.** "You examine the tray and the reply ends by telling you nobody
opened that door" teaches more than "lestrade auto-resolves supported
revelations". This is the note the user gives most often; reach for the worked
example first, not as decoration afterwards.

**Comments describe only the code that is present.** Never reference a diff, a
deleted line, or "the old code" as though the reader can see it — they have the
current file and nothing else. Mechanical check, because this one reads fine as
you write it: the comparative words *used to, no longer, previously, rather
than, instead of, still, was, until now* are the tell. Each time one appears,
name exactly what is being compared, or cut it. If prior behaviour is genuinely
needed to explain the current shape, state what it was and why it changed as
self-contained prose. Before-and-after belongs in the commit message, which is
about the change.

**Name three things to the player, never six.** Orienting someone is not the
same as being complete, and a list long enough to feel like a menu gets skimmed
rather than used. This line was written to a player mid-case and is the mistake:

> board and frontier for taking stock, cast, journal, the notebook (note), and
> casebook if you'd rather leaf through the lot

Six names, and the player kept none of them. What it should have said:

> Taking stock costs you nothing — ask what you've concluded, what threads are
> still open, or to jot something in your notebook, any time.

Three things, no command names, and it reads as an offer instead of a form.
Two specific ways the long version goes wrong, both visible above:

- **Never name a container and its contents in the same breath.** `casebook`
  *is* the cast, evidence, conclusions, notebook and threads pages. Listing it
  alongside `board` and `note` turns one idea into three and makes the player
  wonder how they differ.
- **Never name a command the player cannot type.** The slash commands are
  `/play`, `/new-case`, `/casebook`, `/examine` and `/note`. `frontier`, `cast`,
  `journal`, `hint` and `board` are CLI verbs the narrator runs on the player's
  behalf — the player says "what threads are still open" in English and the
  narrator translates. Reading those names out hands them vocabulary that does
  nothing when typed.

The rule is about what the player hears, not what the engine offers. Everything
stays available; you just stop reciting it.

**Never put where they are standing and what they hold in the same list.** A
comma list reads as one kind of thing throughout, so an item from the case file
sitting beside two items from the room becomes an item in the room. This
recap is the mistake:

> the ballroom, Vane on the floor, Ruth's opened letter in his desk and
> unaccounted for

Three things, and the player has every reason to read all three as within
reach. Two of them are: the room, and the body on its floor. The third is a
clue in the case file, and the desk it was found in is in room four, a storey
up and behind a door. Split the sentence at the seam:

> You're in the ballroom, standing over Vane. In the case file and attached to
> nothing yet: an opened letter to Ruth, found in his desk upstairs.

Say where the detective is, stop, then say what the case file holds. When a
clue names a place, name that place too — "found in his desk upstairs" — because
a clue read out in a room the player is standing in will otherwise borrow it.

**Short sentences, one idea each.**

## Spoiler discipline

This repo can spoil its own content for you, and that is a real hazard when
working in it:

- **`examples/ashgrove.case.json` is the plaintext answer key** to a case that
  may be sitting sealed and unplayed in `cases/ashgrove/`. It is the schema
  reference an authoring LLM imitates, so you will be tempted to read it. If
  the user might ever play Ashgrove, read its *structure* (keys, shapes, counts)
  rather than its contents, and prefer `docs/CASE_SCHEMA.md`.
- `cases/*`, `drafts/`, and `*.key` are gitignored. Drafts are plaintext
  solutions; seal with `--delete-draft`.
- `spoil` is deliberately awkward and appends to `spoilers.log`, which the final
  grade reads. Don't route around it.
- The author skill's warning applies to visible reasoning too: don't think about
  the culprit in text the player can see.
