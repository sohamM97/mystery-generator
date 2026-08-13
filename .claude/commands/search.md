---
description: Turn over the place the detective is standing in
allowed-tools: Bash(python3 -m mystery.cli search:*), Bash(ls cases/*)
---

The player wants to go through this place properly.

## Which case

Use the case currently being narrated in this conversation. If none is in play,
run `ls cases/` — if there is exactly one, use it; if there are several, ask
which before running anything.

## What it is, and what it is not

```
python3 -m mystery.cli search --case cases/<slug>
```

It takes no argument. It searches wherever the detective is standing.

**A place's searchable contents and its examinable contents are different
sets**, and this is the thing players get wrong. Looking around names what is
here and turns nothing up. Examining is the close look at one named thing.
Searching reaches what is attached to no named thing at all — the covered way
lists nothing to examine and holds trodden snow to find. A player who
looked around, was told there was nothing here, and moved on has walked out of
a room with a clue in it. Say the difference the first time it could matter.

## Reading the result

- **`new_clues` — deliver `detail` faithfully.** Rephrase for flow; never add a
  fact, never drop one, never change a number. The numbers are the puzzle.
  Put the find in the room: say where it was and what it is, rather than
  reciting a headline.
- **`NEVER_REVEAL` is absolute.** It carries the clue's reliability and the
  author's note so a liar lies the same way in turn forty. Never surface it,
  never hint at it, and never let your prose grow careful around a false clue.
- **`already_known` means they have been over this place before.** Say so
  plainly and name what they turned up last time; do not re-present it as a
  fresh find. A second search of a room can still be worth running, because
  clues are gated on knowledge and a conclusion drawn since may have opened
  something here — so never tell them searching again is pointless.
- **`nothing_here` is one line, no padding.** Never let the length of your
  reply carry information about what was or wasn't there. And it is not a fact
  about the place: the engine said this search found nothing, not that the room
  is empty or that they are done with it.
- **Withheld content stays invisible.** When the guidance says a clue exists
  but is gated, describe the search as ordinary and unrewarding. Never write
  "something here eludes you."
- **`inferences` are the assist level drawing a conclusion**, not the player
  reaching one. Voice it as the case laying the line down, and say whose
  thinking it was — it will appear on their board marked as the game's, and a
  player who mistakes it for their own has been told they reasoned something
  they never did. **Locate its nouns**, too: the statement was written without
  knowing where the player would be standing when it landed, so a conclusion
  naming the gantry can reach them in a winch house at the foot of the mast.
  Deliver it whole, never reworded, then add the clause that places it — "the
  gantry there being the one at the top of the mast."

Searching costs the player nothing, like everything else they can do. Don't
announce that a place is worth searching, or that it isn't: the engine knows
which rooms hold something and you must not turn that into a nudge.
