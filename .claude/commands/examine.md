---
description: Look closely at something, or see what there is to look at
argument-hint: [the thing to examine · omit to see what is here]
allowed-tools: Bash(python3 -m mystery.cli examine:*), Bash(python3 -m mystery.cli look:*), Bash(python3 -m mystery.cli journal:*), Bash(ls cases/*)
---

## Which case

Use the case currently being narrated in this conversation. If none is in play,
run `ls cases/` — if there is exactly one, use it; if there are several, ask
which before running anything.

## With no argument: what is there to look at

The player wants the room's contents, not a new perception of it.

**First, ask the engine what this room has already shown them.** `journal`
carries `within_reach`: the examinable refs this room named when they looked
around or arrived. Read that list back and say plainly it is what they were
shown.

Do not go hunting through the conversation for an older `look` result. The
engine records this precisely so that a trimmed conversation, or a session that
picked the case up cold, still knows what the detective is looking straight at.

**If `within_reach` is empty** — they have not looked around here yet — run:

```
python3 -m mystery.cli look --case cases/<slug>
```

Run it too whenever they ask to look again rather than be reminded. It costs
them nothing, and a room can name something it could not name before, because
clues are gated on knowledge: a conclusion drawn since their last look may
have opened something here. Don't run it speculatively on their behalf, though.
Watching the list grow after each deduction is a nudge they didn't ask for, and
the reminder in `within_reach` is what answers "what's here?"

Read the list back as things within reach, not as an inventory screen. Anything
`examinable` names that the room's description never mentioned gets said in
prose first — a `body` in the list means a man is lying on the floor, and
listing him between a coat and a lamp buries him.

## With an argument: look closely at it

```
python3 -m mystery.cli examine --case cases/<slug> "$ARGUMENTS"
```

**If they have already examined this thing in this conversation**, say what
they already hold and offer the second look rather than silently repeating the
first. A second look returns the same thing unless something has changed since
— but it can, because clues are gated on knowledge, so never tell them a second
look is pointless.

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
