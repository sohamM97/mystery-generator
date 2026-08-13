---
name: new-case
description: Generate a new sealed mystery for the player to solve. Use when the user asks for a new case, a new mystery, a new whodunit, or wants to play a fresh story. Takes an optional premise (setting, era, tone, cast size, difficulty).
---

# Authoring a case

You are the author, not the narrator. Your job ends when a case is sealed. Do
not begin narrating; do not tell the user anything about the solution, and be
careful not to leak it in your visible reasoning either. If you must think
about the culprit out loud, don't — think about it in the draft file.

## Procedure

1. **Agree the premise.** Setting, era, tone, cast size (6–8 including the
   victim), difficulty. If the user gave a premise, use it and don't
   interrogate them. If they gave nothing, pick something and say what you
   picked in one line.

2. **Write the truth first, backwards.** Decide who, why, and *how* before you
   write a single clue. Then ask: what did that leave behind? Every clue in the
   case should be the residue of something in the timeline. Clues invented
   forward, to be found, feel like clues. Clues derived backward, from events,
   feel like the world.

3. **Draft to `drafts/<slug>.case.json`.** Follow `examples/ashgrove.case.json`
   exactly — it is the schema reference, and it is a case that passes every
   check. `docs/CASE_SCHEMA.md` explains each field.

4. **Validate until clean:**
   ```
   python3 -m mystery.cli validate drafts/<slug>.case.json
   ```
   Fix every error. Fix warnings unless you can say why the warning is wrong.
   The validator is not a formality — it catches unsolvable cases, circular
   reasoning, and clues nobody can reach. Expect to fail it the first time.

5. **Seal:**
   ```
   python3 -m mystery.cli seal drafts/<slug>.case.json --assist watson --delete-draft
   ```
   `--delete-draft` matters. A plaintext draft on disk is a spoiler waiting to
   be grepped, by the user or by a future you.

6. **Hand over.** Print the case title and the opening paragraph from
   `cases/<slug>/BRIEF.md`. Nothing else. Tell them to say "play" to begin.

## What makes the case good

**The solution must be inevitable in hindsight and invisible in prospect.**
Everything below serves that.

- **Backwards from the body.** The murder is a *plan* that met an *accident*.
  Give the culprit a scheme that would have worked, and then one thing they
  could not control — the weather, someone's insomnia, their own habit. That
  uncontrolled thing is the case's spine.
- **The culprit's mistake should come from their virtue.** Ashgrove's engineer
  is meticulous, so he signed out the solvent. Not a stupid slip: a character
  trait, visible from act one, that becomes the noose. This is the single
  biggest difference between a mystery that lands and one that merely resolves.
- **Three clues per critical conclusion, from three different places.** The
  validator enforces the count; you enforce the spread. If all three sit in one
  room, a player who skips that room is stuck, and the case only *looks* fair.
- **Two clues that disagree.** The best mysteries have a contradiction the
  player can feel before they can explain — a stopped watch against fallen
  snow. Build one, put both halves early, and let it itch.
- **Red herrings must be true.** Never lie to the player through the narration.
  Lie through *characters*, who have reasons, and mark those clues
  `reliability: "false"` with a `debunked_by`. A frightened man's honest
  mistake is a better herring than an author's trick.
- **Three false solutions, each genuinely arguable.** For each, write the case
  *for* it as a competent detective would, then the single clue that breaks it.
  If you can't argue it, it isn't a false solution, it's a distraction.
- **Knowledge as the key.** Gate at least one location or clue behind a
  conclusion rather than an object. The door that opens because you *understood*
  something is the best feeling in this genre. Don't gate more than two or
  three things or it becomes a corridor.
- **Everyone is hiding something; one of them is hiding this.** Give every
  suspect a secret that is not the murder. It is why the middle of the case is
  interesting.
- **Every examinable object must appear in its room's description.** The
  narrator describes the room from `desc` and nothing else, so an object you
  put in a room without writing it into the prose is invisible: the player can
  only reach it by naming it at random, and that is guessing, not detection.
  A ballroom described as chairs, chalk marks and a ladder, holding an
  examinable `coat`, has a coat nobody in the story can see. Name the object in
  the description and leave what is *interesting* about it to the clue — "a
  scrubbed patch on the floor by the desk" in the room, "the scrubbed patch
  still smells of engineering-grade solvent" in the clue. `validate` reports
  each one it finds as `UNSEEN_OBJECT`.

  **Place it, don't just name it.** "A coat" tells the player a coat exists.
  "He is wearing an overcoat" tells them where it is — which is what anyone
  standing in the room would know without touching anything. The narrator has
  no source for where things are except your description, and it is forbidden
  from guessing, so a named-but-unplaced object passes `validate` and still
  leaves the player asking a question neither of them can answer.

- **A conclusion carries its own geography, because you do not control where
  it is read.** A revelation lands wherever the player happens to be standing
  when the evidence completes, and its statement is delivered to them there.
  This one is written badly:

  > Vane was struck once at the top of the yard steps and went down them
  > backwards; the ladder was stood over him afterwards to explain the injury.

  It reached the player in the scullery yard, which has steps, a coal chute and
  a standpipe and no ladder in it. One sentence, two rooms, and nothing marking
  the join — so they asked what a ladder was doing out there, and they were
  right to. Name the room the moment the sentence leaves the one it started in:

  > Vane was struck once at the top of the yard steps and went down them
  > backwards; the lighting ladder in the ballroom was stood over him
  > afterwards to explain the injury.

  Six words, and the compression stops reading as a contradiction. The test:
  read each revelation statement as though standing in every location in the
  case. If an object in it sounds like it is in the wrong room from any of
  them, say which room it is in. `validate` cannot catch this — it is prose,
  not structure — so it is yours to check.

## Hard rules

- The culprit must be in the cast from act 0 or 1, with lines and presence.
- No solution may depend on information the player cannot obtain.
- No twins, no secret passages, no unknown poisons, no supernatural — unless
  you declare it in `conceits` *and* clue it three times like anything else.
- The victim's death must be reconstructable: time, place, method, and order.
- Write the `truth.narrative` as the last thing you write, in full prose. It is
  the payoff the player earns; it should read like the final chapter, not a
  summary. Make it about a person, not a mechanism.
