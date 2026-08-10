---
description: Jot a line in the detective's notebook during a case
argument-hint: [what you want to write down — omit to read your notes back]
allowed-tools: Bash(python3 -m mystery.cli note:*), Bash(ls cases/*)
---

The player wants to write something down mid-investigation, in their own words:

> $ARGUMENTS

## Which case

Use the case currently being narrated in this conversation. If none is in play,
run `ls cases/` — if there is exactly one, use it; if there are several, ask
which before writing anything.

## What to run

```
python3 -m mystery.cli note --case cases/<slug> "$ARGUMENTS"
```

With no arguments, run it bare — `note --case cases/<slug>` — and read the
notebook back in the order written.

Taking a note is not a turn. It costs nothing and advances nothing; the player
is thinking on paper.

## What to say

One line of acknowledgement, in the detective's voice, then get out of the way
and let play continue.

**Do not react to the content.** Not a word of agreement, correction, emphasis,
or interest. This is the `deduce` hunch rule applied to the player's own
handwriting: a note that is dead right and a note that has swallowed a lie
whole must come back sounding identical. If your acknowledgement of a good note
reads warmer than your acknowledgement of a bad one, the notebook has become a
confirmation oracle and the player will start writing guesses into it to see
which ones you like.

Never write a note on the player's behalf, and never fold in a fact they
haven't been told.
