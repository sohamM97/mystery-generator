# Mystery Generator

Claude writes you a murder. You solve it. The answer is sealed on disk before
play begins, so the story cannot drift, and neither can the narrator.

```
/new-case a locked observatory, 1974, six suspects
/play
```

## Why the seal exists

The obvious way to build this is to ask an LLM to invent a mystery and then run
it. That fails, and it fails in a specific way: fifty turns in, the model has
lost track of who was where, quietly revises the culprit to fit whatever the
player has been theorising, and walks them to a conclusion it has just invented.
The player wins a case that was never solvable. That is worse than losing.

So the model doesn't remember the case. It looks it up.

1. **Author.** Claude writes the whole truth — timeline, cast, every clue, the
   final chapter — into one JSON file.
2. **Validate.** A checker proves the case is fair and solvable before anyone
   plays it. Unreachable clues, circular reasoning, conclusions with too little
   evidence, alibis that can't be broken, red herrings that can't be debunked:
   all rejected. Authoring the example case failed this twice.
3. **Seal.** The file is encrypted. The plaintext draft is deleted.
4. **Play.** Claude narrates, but every fact it states comes from a scoped
   query against the sealed file, made in that turn. It never recalls; it reads.

The result: the culprit was decided before your first question and cannot
change, and the case was proven winnable before you were allowed to start.

## Assist levels

Your critique of the genre — that these games make the inferences for you and
leave you filling gaps — is a dial here, not a fixed design.

| level | who does the thinking |
|---|---|
| `holmes` | You. Nothing is inferred for you, ever. Outer Wilds. |
| `watson` | Routine steps resolve themselves; every conclusion that matters is yours. **Default.** |
| `lestrade` | The game voices each deduction the evidence supports and you follow the thread. Danganronpa. |

Switch mid-case: `python3 -m mystery.cli assist --case cases/<slug> holmes`.

### The same clue at all three levels

The Ashgrove brief hands every player the same opening: Dr Rask at the foot of
the transmitter mast, skull broken, **spectacles folded neatly in his breast
pocket**. You go and look at the body.

A man does not fold his spectacles on the way down. Say the conclusion sitting
on top of that is *he didn't come off that mast — someone put him there*.

**lestrade.** You examine the body, and the reply ends:

> His spectacles are folded in his breast pocket, unbroken. **He did not come off
> that mast. Someone laid him at the foot of it.**

That second thought isn't yours. The game drew it the instant the clue landed,
and your case file logs it `drawn by: the game`. You follow where it leads.

**watson.** You examine the body and get the broken skull, the folded
spectacles, and nothing else — *if* this is a conclusion that matters.

Every conclusion in a case is marked by its author as either part of the chain
that proves who did it, or a connecting step that just gets you from one fact to
the next. Watson resolves the connecting steps quietly, so you find them already
in your file, and never touches the chain. A conclusion on the chain sits there
fully evidenced and **waits** — the game will not say it, however long you
stare. You say *"nobody falls with their glasses put away — he was moved"*, and
it lands.

**holmes.** You get the skull and the folded spectacles. That is all you will
ever get. Nothing moves until you say the sentence yourself, and your case file
lists the conclusion without the spectacles underneath it — what proved what is
your memory and your notes page.

Identical at all three: the same clues in the same places behind the same gates,
the same evidence threshold (the conclusion needs the spectacles in hand at
holmes exactly as at lestrade), a hunch that never leaks warm or cold, and a
final grade that doesn't care which level you played. **The dial changes who
does the thinking, not how hard the case is.** A holmes player and a lestrade
player see the identical body; one of them gets told what it means.

## The case file

Everything the case has given you, and the one page it hasn't:

| section | what it holds | who fills it |
|---|---|---|
| evidence | every clue found, in full | the engine, on discovery |
| conclusions | what's established, and what proved each | the engine, tagged `drawn_by` |
| suspicions | things you said aloud and didn't prove | the engine, in *your* words |
| notes | anything you type | only you |

```
python3 -m mystery.cli journal --case cases/<slug>   # the whole file
python3 -m mystery.cli board   --case cases/<slug>   # conclusions and what carries them
python3 -m mystery.cli note    --case cases/<slug> "pike went quiet when the boiler came up"
```

The notes page is yours and the engine never grades it: write down a lie a
witness told you and it comes back exactly as you wrote it. Notes are numbered
and editable — `--strike N` rules a line through and leaves it legible,
`--amend N` writes a replacement underneath, `--rewrite N` fixes the wording in
place. Nothing erases.

Suspicions are recorded in your words whether or not the case has anything
behind them, so the list itself tells you nothing — which is the point.

## Being wrong

You can accuse the wrong person. Every case ships three false solutions, each
one a theory a competent detective would actually build, each broken by one
specific clue. Convict the wrong suspect and you get the clue you read past,
and what happened to them.

Accusations are graded on two axes, because being right is not the same as
detecting. `airtight` means you named the culprit and could prove it.
`lucky guess` means you named the culprit.

## Peeking

`cases/<slug>/seal.key` sits next to the sealed case, so of course you can
decrypt it. That's deliberate: this is a lock on a diary, not a safe. It stops
accidental spoilers — a stray `grep`, an editor tab, a future Claude reading
the repo — and makes deliberate ones cost something:

```
python3 -m mystery.cli spoil --case cases/<slug> culprit --yes
```

which is recorded in `spoilers.log`, which the final grade reads. The honest
version of "you can cheat" is "you can cheat, and the score will know."

## Layout

```
mystery/            engine, validator, seal, CLI
  schema.py         what a case is
  validate.py       fair-play checks — Knox, Van Dine, the Three Clue Rule
  engine.py         play state, knowledge-gating, deduction, grading
  seal.py           encryption at rest
examples/           ashgrove.case.json — reference case, PLAINTEXT, spoiled by design
cases/<slug>/       sealed, playable
docs/DESIGN.md      the craft research this is built on
tests/              end-to-end playtest: python3 tests/test_playthrough.py
```

**`examples/ashgrove.case.json` contains its own solution in the clear.** It is
the schema reference and the model an author-LLM imitates. Don't read it if you
ever want to play it — ask for a fresh case instead.

No dependencies. Python 3.10+.
