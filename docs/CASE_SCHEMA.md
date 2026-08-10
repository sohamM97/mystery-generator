# Case schema

One JSON file holds an entire mystery. `examples/ashgrove.case.json` is a
complete, validating instance — read it alongside this.

## Top level

| field | required | meaning |
|---|---|---|
| `meta` | yes | `slug`, `title`, `setting`, `era`, `tone`, `difficulty` |
| `opening` | yes | The paragraph the player is given before anything else |
| `cast` | yes | Everyone, victim included |
| `locations` | yes | The map. First entry is where play begins |
| `clues` | yes | Every discoverable fact |
| `revelations` | yes | Every conclusion the detective can reach |
| `timeline` | yes | What actually happened, minute by minute |
| `truth` | yes | The answer key |
| `false_solutions` | 2+ | Wrong answers the case genuinely supports |
| `conceits` | no | Declared genre allowances (twins, secret passage) |

## cast[]

`id`, `name`, `role`, `public_desc`, `introduced_at` (act index — the culprit's
must be in the first third), `secrets[]` (never shown; keeps the narrator
consistent), `locked_topics{topic: revelation_id}` (this character deflects
until you know something).

## locations[]

`id`, `name`, `desc`, `connects[]`, `gates[]` (revelation ids — the location is
invisible and unreachable until they're held).

## clues[]

| field | meaning |
|---|---|
| `id`, `kind` | `physical` / `testimony` / `document` / `observation` / `absence` |
| `headline` | One line. This is what the journal shows |
| `detail` | What the narrator describes. Numbers here are the puzzle — never altered |
| `source` | `{kind: examine\|ask\|search, at: <loc>, ref: <object or character>, topic: <for ask>}` |
| `gates[]` | Revelations required before this is findable |
| `supports[]` | Revelations this is evidence for. **Must be mirrored** in that revelation's `clues[]` |
| `reliability` | `hard` (true), `soft` (true but misleading), `false` (a character is lying) |
| `debunked_by[]` | Required when `reliability: false`. Clue ids that expose it |
| `hidden_note` | Never shown. How to keep a liar lying the same way in turn forty |

The `supports` ↔ `clues` mirror is enforced. Asymmetry means the author changed
their mind halfway and left the case in two states.

## revelations[]

`id`, `statement`, `requires[]` (other revelations — must form a DAG),
`clues[]`, `support_needed` (how many the player must hold before the engine
accepts the conclusion), `critical` (part of the solution chain — needs three
trustworthy clues instead of two), `nudge` (the hint text; points at evidence,
never at the conclusion).

Put `method` in the id of the revelation that explains *how* the crime was
done — Knox #4 is checked by looking for it.

## timeline[]

`t` (minutes past midnight), `actor`, `location`, `action`, `witnesses[]`,
`trace` (the clue this event leaves behind). Checked for actors being in two
places at once, and for the culprit having actual opportunity within thirty
minutes of `truth.time`.

Write this before you write a single clue.

## truth

`culprit`, `method`, `motive`, `weapon`, `time`, `accomplices[]`, and
`narrative` — the full final-chapter prose, released only on a correct
accusation. Write it last, and write it about a person.

## false_solutions[]

`id`, `culprit`, `pitch` (the case *for* this theory, argued properly),
`refuted_by[]` (clue ids — must be reachable), `consequence` (what happens to
the innocent person you convicted).

## Validation

```
python3 -m mystery.cli validate drafts/<slug>.case.json
```

Errors block sealing. The codes: `BAD_REF`, `DUP_ID`, `CYCLE` (circular
reasoning), `THREE_CLUE`, `LINK_ASYMMETRY`, `UNSATISFIABLE`, `KNOX_1`,
`KNOX_4`, `TIMELINE`, `NO_OPPORTUNITY`, `UNREACHABLE`, `UNFAIR_HERRING`,
`UNFAIR_ALT`, `NO_SOLUTION`, plus warnings `SINGLE_SOURCE`, `THIN_CAST`,
`THIN_ALTS`.
