---
description: Lay out what the detective has concluded, and what proved it
allowed-tools: Bash(python3 -m mystery.cli board:*), Bash(ls cases/*)
---

The player wants to see where the case stands.

## Which case

Use the case currently being narrated in this conversation. If none is in play,
run `ls cases/` — if there is exactly one, use it; if there are several, ask
which before running anything.

## What to run

```
python3 -m mystery.cli board --case cases/<slug>
```

Free, untimed, and not a turn. It contains nothing the player hasn't already
earned, so it costs them nothing to look — and it is not counted in the grade
the way `hint` is.

## What to say

Render it as the detective laying it out on the table: each conclusion with the
evidence that carries it underneath, in the detective's own voice rather than as
a data dump.

- **`drawn_by` is not decoration.** `you` means the player reasoned their way
  there; `the game` means the assist level handed it to them. Keep the two
  visibly apart. Don't praise the earned ones or apologise for the handed ones —
  just never let a player mistake the game's reasoning for their own.
- **`unattached_clues`** are things in hand that none of their conclusions use
  yet. Read them out flatly as loose ends. Never say or hint at what they might
  prove.
- **`suspicions`** are the player's own unproved statements, in their own words.
  Give every one the same weight — you are not told which of them the case can
  back, and the ones that are right must not read any warmer than the ones that
  are wrong.
- **Nothing here looks forward.** Do not append a "so the next step is" of your
  own. If they want a push, that is `frontier`, or a `hint` they ask for.

At `holmes` the board carries the conclusions and none of the wiring — no
supporting clues. Render what you're given and don't fill the gap from memory.
