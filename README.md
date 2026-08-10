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
