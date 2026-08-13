---
description: Jot, strike, or amend a line in the detective's notebook during a case
argument-hint: [what to write down · "strike 3" · "3: better wording" · omit to read back]
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
python3 -m mystery.cli note --case cases/<slug> --strike N
python3 -m mystery.cli note --case cases/<slug> --unstrike N
python3 -m mystery.cli note --case cases/<slug> --amend N "the new wording"
python3 -m mystery.cli note --case cases/<slug> --rewrite N "the new wording"
python3 -m mystery.cli note --case cases/<slug> --tear-out N
```

With no arguments, run it bare — `note --case cases/<slug>` — and read the
notebook back in the order written, **with its numbers**. The numbers are how
the player addresses a line; a read-back without them is useless to them.

Read the player's intent off their phrasing, the same way you match a `deduce`:

- *"strike 3"*, *"scratch that last one"*, *"3 is wrong"* → `--strike N`
- *"put 3 back"*, *"actually 3 was right"* → `--unstrike N`
- *"I was wrong, it's actually ..."* → `--amend N "..."` (they changed their mind)
- *"2 should say ..."*, *"fix the wording on 3"* → `--rewrite N "..."` (they wrote it down badly)
- *"delete 4"*, *"that's a duplicate"* → `--tear-out N`
- anything else → a plain new note

The distinction that matters is **amend vs rewrite**. `--amend` is for changing
your mind: it strikes the old line and writes the new one underneath, because
having believed the old thing is part of the player's reasoning and belongs on
the page. `--rewrite` is for fixing how a line got written down — a misheard
figure, a sentence that came out wrong — and replaces the wording in place,
keeping the number. When you can't tell which they mean, ask in half a sentence;
guessing `--tear-out` is the only guess that loses something.

Numbering never shifts. A struck line keeps its number, and a torn-out line's
number is never reused.

If a number doesn't exist the result comes back `ok: false` — the detective
looks for that line, doesn't find it, and says so. Don't guess which line they
meant; if the reference is ambiguous, read the notebook back and let them point.

None of this reaches the final read-out. The notebook is the player thinking on
paper, and nothing they write in it is counted or read back at the end.

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

This covers striking and amending too, and it is easiest to break there. Never
imply the struck line was the wrong one or that the new wording is an
improvement — no "good catch", no "that's clearer". Striking a true note and
striking a false one must read identically, or the player has found a way to
test their notes against the truth by proposing to cross them out.

When you read the notebook back, read the struck lines out with the rest, in
place, visibly struck (`~~like this~~`). A notebook that hides what the player
stopped believing is a notebook that has edited their reasoning for them.

Never write a note on the player's behalf, and never fold in a fact they
haven't been told.
