# ADR 0030 — The Draft Summary: its shape, its inputs and its evals

**Status:** Proposed · **Date:** 2026-10-15 · **Amends:** ADR 0024 §5 (the brief), §7 (structured output) and §9 (prompts and evaluation), for the Draft Summary only · **Relates to:** ADR 0025 (the Reviewed Deck), ADR 0026 and 0028 (Deck Ratings, Colour Sources and land targets), ADR 0029 (HOB only)

---

## Context

ADR 0024 settled that one Claude Sonnet 5.5 call writes a Draft Summary
for each Reviewed Deck, with hindsight, after the deck is submitted. It
left open what the summary looks like, what its brief holds and how it is
evaluated. Phase 4a built the Pick Note machinery (`briefing/`, `llm/`,
`llm_calls`, the spending cap, the eval harness) and Phase 4b the deck
metrics and Deck Ratings, so the summary can reuse both. These decisions
were settled with Jackson on 2026-10-15.

## Decision

### 1. The output: four fixed fields (S1)

The summary is structured output with fixed fields, not free prose:

| Field | What it says | Target | Cap |
|---|---|---|---|
| `draft_arc` | the colours taken, the signals, what wheeled | about 60 words | 75 |
| `deck` | the deck's strengths and weaknesses, tied to its Deck Ratings | about 100 words | 125 |
| `lesson` | one thing to carry into the next draft | about 40 words | 50 |
| `key_picks` | up to two picks the UI links to | at most 2 | 2 |

Each `key_picks` entry is a pick reference (`pack_number`, `pick_number`)
and nothing else. Python fills in the card taken, the verdict and the gap
when it renders, as it does for a Pick Note, so the prose can never
contradict the label. A reference to a pick the draft does not have fails
validation. The targets are in the prompt; the caps, 1.25 times the
targets and placeholders, are checked on every call and by the eval.

Fixed fields let the UI lay the summary out (the arc beside the pick list,
the deck beside the ratings panel) and let the eval check each part's
length on its own.

### 2. The brief (S2)

`briefing/summary.py` turns a `DraftAnalysis`, a `Deck`, its
`DeckMetrics` and `DeckRatings`, and the card facts into the brief. Every
number is display text from `briefing/format.py`, as in 4a. It holds:

- **The pick record**: one line per pick (its number, the card taken, the
  verdict, and the gap to the best card), for all 42 picks.
- **The Noted Picks in full**: for each, the best card, the gap, where it
  comes from part by part, and its largest part. **No Pick Note prose**: a
  note may not exist yet, since notes are written on click (ADR 0024 §3),
  and the summary must not depend on which ones were opened.
- **Hindsight facts**: the wheels per pack (good cards wheeled and cards
  the table took, by colour, and each above-average card that wheeled,
  with its win rate and its ALSA), and the leading pair at the end of the
  draft.
- **The Reviewed Deck**: its cards, with cost, type and GIH WR, its basics,
  and every metric with its value, percentile and grade, the predicted win
  rate and the overall grade. The ratings carry the line "Grades are
  relative to 17Lands players, who play better than average: a C is an
  average 17Lands deck" (ADR 0026).
- **The mana facts**: the largest Colour Source shortfall, with its spell
  ("needs 10 red sources; the deck has 7.0"), and the count of spells short
  (ADR 0028 §3); the effective land count against its target.
- **At most one notable omission**, as a fact (ADR 0025 §4).

Oracle text is left out of the summary's brief. The summary is about the
draft and the deck as a whole, and 40 cards' text would triple the brief.
The prompt forbids rules claims the brief does not support.

### 3. The format primer

Cached block 2 (ADR 0024 §6) is the **Format Primer**, built by
`briefing/primer.py` from `archetype_stats` and `card_draft_stats`: each
colour pair's win rate and games, the format's average GIH WR, and the
five best commons of each colour by GIH WR. ADR 0024 also named the
format's speed; there is no measured speed statistic, so the primer leaves
it out rather than invent one. It changes only when a new Stats Snapshot
is ingested, so it is byte-identical across drafts of the same format.

### 4. The prompt, the model and the call

- **`docs/prompts/draft_summary.v1.md`**, on `claude-sonnet-5-5` at `low`
  effort, with the API's server-side refusal fallback (`fallbacks:
  "default"`, beta `server-side-fallback-2026-07-01`; it retries some
  refusal categories on Claude Sonnet 5).
- **Layout**: system block 1 is the prompt (instructions and few-shot
  examples), system block 2 is the format primer, both with the 1-hour
  cache lifetime. The draft's brief is the user message, last.
- **The call** follows `llm/pick_note.py`: `messages.create` with
  `output_config.format`, validated against the Pydantic model and then by
  the checks of §1 and the invented-number check, retried once, every call
  recorded in `llm_calls` with purpose `draft_summary`, and the spending
  cap checked before each attempt. A refusal of the whole fallback chain
  is not retried.
- **Cost with a fallback**: when a fallback served the response, the
  response's `usage.iterations` lists each attempt and the model that ran
  it. The cost is summed over the attempts, each at its own model's
  price, and `llm_calls.model` records the model that served the
  response. No schema change is needed.

### 5. The evals (S3)

- **Two fixture decks from the HOB golden draft** (hob.d9ac6765), built by
  Jackson: the deck he would have played, and a deliberately flawed copy
  (for example 15 lands, and too few sources for a pip-heavy card). Each
  is a JSON file of 40 card names, basics included, in
  `api/tests/fixtures/decks/`, with the flaw named in the flawed file.
- **Offline, every run**: the decks build from the pool, their briefs
  hold the facts above, the cached blocks are byte-identical across
  drafts, and the prompt's own examples pass the live checks against
  the briefs they were drafted from.
- **Live, when asked** (`DRAFT_SUMMARY_EVAL=1`): the JSON validates, no
  number appears that the brief does not state, each field is within its
  cap, the key picks exist, and the flawed deck's summary names its flaw.
- **Claude Haiku 5.5** runs through the same live eval
  (`DRAFT_SUMMARY_MODEL=claude-haiku-5-5`), without the fallback, which
  Haiku does not have, so the two can be compared (ADR 0024 §4).

### 6. The few-shot examples (S4)

About two example summaries, drafted by Claude from the public-dataset
draft hob.5d9123f8 (which the eval never grades), with a deck built from
its pool for each, and rewritten by Jackson. Their briefs in the prompt
are trimmed, but the eval checks each example against the full brief of
its deck.

### 7. The CLI

`scripts/write_draft_summary.py DRAFT DECK` writes a summary for a stored
draft and a deck fixture, recording the call in `llm_calls` with no user,
as `scripts/write_pick_notes.py` does for notes. `--dry-run` prints the
brief and the primer and calls nothing.

## Considered options

- **Free prose** was rejected: the UI could not place its parts, and a
  length cap on the whole would not stop one part crowding out another.
- **Pick Note prose in the brief** was rejected. Notes are written on
  click, so the summary would change with what the user happened to open.
- **Oracle text for every deck card** was rejected as too large for what
  it adds to a summary of the whole.
- **Key picks with their details written by Claude** were rejected, for
  the same reason as the Pick Note's verdict: Python already knows them.
- **A flaw check by keyword list in code** was rejected in favour of the
  flaw named in the fixture, since only the fixture's author knows what
  the flaw is.

## Consequences

- The Draft Summary has no endpoint yet: Phase 5 adds it, with the deck
  builder.
- `llm.pricing` gains Claude Sonnet 5's price, for calls a fallback
  served.
- The eval's live run costs a few cents per deck on Sonnet.

**Revisit when:** the live eval shows Haiku writes summaries as well as
Sonnet (switch, as ADR 0024 §4 says); a field keeps hitting its cap; or
the summary names the same lesson for every draft.

**Glossary:** Format Primer and Key Pick are added to `CONTEXT.md`.
