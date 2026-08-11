---
description: Look closely at something, or see what there is to look at
argument-hint: [the thing to examine · omit to see what is here]
allowed-tools: Bash(python3 -m mystery.cli examine:*), Bash(python3 -m mystery.cli look:*), Bash(ls cases/*)
---

## Which case

Use the case currently being narrated in this conversation. If none is in play,
run `ls cases/` — if there is exactly one, use it; if there are several, ask
which before running anything.

## With no argument: what is there to look at

The player wants the room's contents, not a new perception of it.

**First, check whether you already have them.** Every `look` and every `go`
returns `examinable` for that room. If one of those results for the room they
are standing in is already in this conversation, read the list back from it.
That is free and spends no turn: it is not the engine telling you something
new, it is you repeating what it already said. Say plainly that this is what
you were shown when they arrived.

**Only if you have no such result** — they have been moved by something else,
or the conversation has been trimmed — run:

```
python3 -m mystery.cli look --case cases/<slug>
```

`look` **is a turn.** Tell them before you spend it, not after, and let them
decline. A player who asked "what's here?" expecting a reminder and got charged
for a fresh look around has been billed without being told the price.

Read the list back as things within reach, not as an inventory screen. Anything
`examinable` names that the room's description never mentioned gets said in
prose first — a `body` in the list means a man is lying on the floor, and
listing him between a coat and a lamp buries him.

## With an argument: look closely at it

```
python3 -m mystery.cli examine --case cases/<slug> "$ARGUMENTS"
```

This is a turn, whether or not it finds anything.

**If they have already examined this thing in this conversation**, say what
they already hold and ask whether to spend the turn on a second look, rather
than spending it for them. A second look returns the same thing unless
something has changed since — but it can, because clues are gated on
knowledge, so never tell them a second look is pointless. Ask.

## Reading the result

- **Deliver `detail` faithfully.** Rephrase for flow; never add a fact, never
  drop one, never change a number. The numbers are the puzzle.
- **`NEVER_REVEAL` is absolute.** It carries the clue's reliability and the
  author's note so a liar lies the same way in turn forty. Never surface it,
  never hint at it, and never let your prose grow careful around a false clue.
- **An empty result is not a fact about the thing.** `nothing_here` can mean
  the thing is here and holds nothing, that it is in the next room
  (`at_hand_elsewhere`), or that there is nothing of that name where they are
  standing (`unknown_target`). Read the flags and say the right one. "The tray
  gave you nothing" is a claim about the world the engine never made, and it
  will contradict the real clue later.
- **Withheld content stays invisible.** When the guidance says a clue exists
  but is gated, describe the thing as ordinary. Never write "something here
  eludes you."
- **Nothing found means nothing found.** One line, no padding. Never let the
  length of your reply carry information about what was or wasn't there.
