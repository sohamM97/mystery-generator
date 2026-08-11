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
case's own `meta.difficulty`, which is baked in when the case is authored.

Tell them what else is on the table, because none of it is discoverable and all
of it is free: `board` (what you've concluded, and what proved it), `frontier`
(threads you haven't pulled), `note` (your own notebook, editable), and `hint`
— which costs nothing but is recorded and read out with the final verdict, and
they should hear that *before* they spend one, not after.

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

- **plumbing** for unimportant machinery. Say what it is: non-critical
  conclusions, connecting steps, bookkeeping.
- **load-bearing** for important. Say why: "the game dissolves if this leaks",
  "every other check depends on it".

A boiler or a pipe *in a case* is a boiler and a pipe — the ban is on the
metaphor, not the noun. Add future entries here.

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
