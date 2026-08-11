---
description: Open the casebook, or read one of its pages out
argument-hint: [cast · evidence · conclusions · notebook · threads · omit to open it yourself]
allowed-tools: Bash(python3 -m mystery.cli casebook:*), Bash(ls cases/*)
---

The player wants the casebook: their own records, laid out on pages.

## Which case

Use the case currently being narrated in this conversation. If none is in play,
run `ls cases/` — if there is exactly one, use it; if there are several, ask
which before running anything.

## Two ways to read it, and only one of them is yours

The full-screen casebook is **theirs to run, not yours**. It is a curses view
that takes over the terminal, and you cannot drive it or see it.

**It needs a real terminal, and running it through Claude Code does not give
it one.** A `!` command has its output captured, so the program finds no
terminal, says so on stderr, and prints all five pages flat. That is a
perfectly good way to read the casebook — it is just not the paged one. Do not
tell the player to type `!python3 -m mystery.cli casebook ...` and expect pages
to appear; they will get the flat print and wonder what they did wrong.

So when they ask for the casebook with no page named, offer both plainly:

- Read it here — you run `casebook --case cases/<slug>`, which prints every
  page, or `--page <name>` for one of them.
- Leaf through it — they open a terminal of their own, outside Claude Code,
  and run `python3 -m mystery.cli casebook --case cases/<slug>`, where ←/→
  move between pages, ↑/↓ scroll, and `q` closes it.

One line each. Don't push them towards the terminal, and don't narrate over it.

If they named a page — `$ARGUMENTS` — or if they clearly want it read aloud
rather than opened, print that page instead:

```
python3 -m mystery.cli casebook --case cases/<slug> --page <name>
```

The pages are `cast`, `evidence`, `conclusions`, `notebook` and `threads`.
Match what they said to one generously: "who's who" is `cast`, "what have I
got" is `evidence`, "what do I know" is `conclusions`, "my notes" is
`notebook`, "what's left" is `threads`. If nothing matches, ask which page
rather than guessing — printing the wrong one wastes their attention, though
not a turn.

Free, untimed, and not a turn, exactly like the views it is built from. It
holds nothing the player has not already earned, which is why it costs nothing
to look.

## What to say

The command prints the page ready to read. Pass it on as the detective's own
records — you may set it down in a line ("your own notes, as you left them")
but do not rewrite the page, reorder it, or summarise it.

Everything the `board` command's own rules say applies here too, because the
conclusions page is the board:

- **`drawn_by` is not decoration.** A conclusion the page marks as the game's
  was handed to the player by the assist level. Never let them mistake it for
  their own reasoning.
- **Loose ends are named, never explained.** Say what they are and stop.
- **Suspicions carry no weight.** You are not told which of the player's own
  unproved statements the case can back, so give every one the same register.
- **Nothing here looks forward.** Do not append a "so the next step is". If
  they want a push, that is `frontier`, or a `hint` they ask for.

On `holmes` the conclusions page carries no supporting evidence and the threads
page reports no count of conclusions already carried. That is deliberate.
Render what you are given and never fill the gap from memory.
