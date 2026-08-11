# Design notes

What the research says, and what each finding turned into in code.

## 1. Fair play is older than the genre's reputation

Ronald Knox's Decalogue (1929) and S.S. Van Dine's Twenty Rules (1928) are
usually cited as quaint. Read as a spec they are surprisingly mechanical:

> The reader must have equal opportunity with the detective for solving the
> mystery; all clues must be plainly stated and described.

Several of these are directly checkable, so `validate.py` checks them:

| Rule | Check |
|---|---|
| Knox #1 — the culprit must appear early | `KNOX_1`: culprit's `introduced_at` must fall in the first third of acts |
| Knox #4 — no undiscovered poisons, no unexplained science | `KNOX_4`: the method needs its own critical revelation, clued like anything else |
| Knox #3 / #10 — one secret passage, no undeclared twins | `conceits` must be declared, and are then clued like anything else |
| Van Dine #15 — the truth must be apparent in retrospect | The solvability simulation: a perfect detective must reach every critical conclusion |
| Fair play generally | Every red herring needs a reachable `debunked_by`; every false solution a reachable refutation |

The rules were written as a promise to the reader. A promise you can test is
better than a promise you make.

## 2. The Three Clue Rule

Justin Alexander, on running mysteries at a table:

> For any conclusion you want the PCs to make, include at least three clues.
> Players will probably miss the first, ignore the second, and misinterpret the
> third.

No other borrowing here does as much work. It survives the
translation from tabletop to software intact, because the failure it prevents —
the investigation that dead-ends because one clue was missed — is the same
failure. `THREE_CLUE` enforces three for critical conclusions, two for
supporting ones, and `SINGLE_SOURCE` warns when all three sit in the same room,
because three clues in one place is one clue wearing a disguise.

Alexander's **node-based** extension matters too: clues are either *evidence*
(pointing at a conclusion) or *leads* (pointing at more clues). Modelled as
`supports` and `gates` respectively, which is what makes the case a graph
rather than a corridor.

## 3. Verification without trial-and-error

*Return of the Obra Dinn* solves a hard problem: how do you confirm a player's
deduction without letting them brute-force it? Its answer is to confirm in
batches of three, so guessing is possible but tedious enough to be pointless.
*The Roottrees are Dead* takes the same approach.

We can't batch, because deductions arrive one sentence at a time in prose. So
the engine uses a different lock: **you cannot be told whether you are right
until you can show why.** State a conclusion without the evidence and it is
recorded as a *hunch* — and crucially, the response does not reveal whether the
hunch is correct. There is nothing to fish for. The instruction to the narrator
on this path is the strictest in the repo, because a narrator that leaks
warm/cold here dissolves the entire game.

This also produces the grading axis: correctness and provability are scored
separately. `lucky guess` is a real ending.

## 4. Multiple solutions, honestly built

*Sherlock Holmes: Crimes & Punishments* ships 3–5 solutions per case and lets
you convict an innocent person, permanently. That only works if the wrong
answers are *honestly reachable and honestly refutable* — otherwise it is a gotcha.

So `false_solutions` is a first-class part of the schema, and the validator
rejects any that lack a reachable refutation, plus warns when a case ships
fewer than two. Each carries a `pitch` (the case *for* it, written as a
competent detective would build it) and a `consequence` (what happens to the
person you convicted). The consequence is what makes the accusation feel like a
judgement instead of a quiz answer.

## 5. Knowledge as the key — the Outer Wilds axis

The stated problem with the genre: these games hand you the inferences and
leave you filling gaps. *Outer Wilds* is the counter-example because nothing in
it is gated by an object. You always could have flown there; you didn't know to.

Two mechanisms carry this:

- **Knowledge gates.** Locations and clues carry `gates: [revelation_id]`. In
  the example case the winch house is invisible until you conclude that nobody
  climbed the mast — the door opens because you *understood* something. The
  narrator is instructed to describe gated content as ordinary, never as
  withheld, because "something here eludes you" is item-gating with extra steps.
- **Assist levels.** `holmes` infers nothing for you, `lestrade` infers
  everything, `watson` splits it: the connecting steps resolve themselves, every
  *critical* conclusion is yours. That last one is the specific complaint,
  addressed directly — the game does the bookkeeping you'd find tedious and
  none of the thinking you'd find satisfying.

The `frontier` command is *Outer Wilds*' ship log: it reports which places and
people still have threads, and a bare count of conclusions your evidence would
already support. Shape, never content. It tells you that you have enough; it
never tells you what for.

## 6. Danganronpa's contribution

The class trial is a *contradiction* engine: testimony is presented, and you
shoot the inconsistent part with the evidence that breaks it. What survives
here is the design instinct that **a lie is more interesting than a gap**.

Hence `reliability: false` clues with `debunked_by`. A false clue is not the
author deceiving the player — the narration never lies. It is a *character*
lying, for reasons, and the engine holds the note that keeps them lying
consistently across forty turns. In the example case, one man's lie is fear and
another's is guilt, and only one of them killed anybody.

## 7. Why the truth is written backwards

The authoring skill requires the timeline before the clues. Clues invented
forward — "what should the player find?" — read as clues. Clues derived
backward from events — "what did this leave behind?" — read as a world.

The related rule, which does more work than any other piece of craft advice
here: **the culprit's mistake should come from their virtue.** The Ashgrove
engineer is undone because he is meticulous, and signed out the solvent he used
to clean the floor. That trait is visible from his first scene. It is not a
slip; it is a character. This is the difference between a mystery that lands
and one that merely resolves.

## Sources

- [Knox's Decalogue and the Detection Club Oath](https://theinvisibleevent.com/2019/03/02/the-men-who-explain-miracles-episode-9-2/)
- [The "Rules" of Detective Fiction](https://agathachristie.fandom.com/wiki/The_%E2%80%9CRules%E2%80%9D_of_Detective_Fiction)
- [Van Dine's Twenty Rules](https://amberfoxxmysteries.com/tag/van-dines-twenty-rules-for-mysteries/)
- [The Alexandrian — Three Clue Rule](https://thealexandrian.net/wordpress/1118/roleplaying-games/three-clue-rule)
- [The Alexandrian — Node-Based Scenario Design: Inverting the Three Clue Rule](https://thealexandrian.net/wordpress/7985/roleplaying-games/node-based-scenario-design-part-3-inverting-the-three-clue-rule)
- [The Roottrees are Dead, or, 5 Easy Pieces — Spectre Collie](https://spectrecollie.com/2026/08/08/the-roottrees-are-dead-or-5-easy-pieces/)
- [Roottrees vs Obra Dinn — deduction games compared](https://www.the-incident-at-galley-house.wiki/roottrees-are-dead/roottrees-vs-obra-dinn/)
- [Sherlock Holmes: Crimes & Punishments — deduction board and multiple solutions](https://en.wikipedia.org/wiki/Sherlock_Holmes:_Crimes_%26_Punishments)
- [Danganronpa Class Trials](https://danganronpa.fandom.com/wiki/Class_Trials)
