# ADR 0024 — Pick Notes and the Draft Summary

**Status:** Proposed · **Date:** 2026-10-15 · **Supersedes:** development plan §4.2 (per-pack batching, a blurb for every pick, the echoed verdict) and §4.4 item 4 (Haiku for card-name resolution) · **Amends:** ADR 0008 §3 (only a mistake earns a note), ADR 0020 §5 (what a practice draft stores) · **Relates to:** ADR 0021 (no account, no Claude), ADR 0025 (the Submitted Deck), ADR 0026 (Deck Ratings), ADR 0027 (limits)

---

## Context

Phase 4 was planned on 2026-08-24, before the grading ADRs. Its §4.2
expected a written blurb for every pick, produced by one call per pack and
a fourth summary call. ADR 0008 then decided that only a `mistake` earns a
note. On the HOB golden draft that is zero notes: 34 solid, 5 indifferent
and 3 questionable picks, the questionable gaps all between 2.2 and 2.42pp.

Practice drafts (ADR 0020) add a second place where Claude could speak:
during the draft, while the next pick is still to come.

## Decision

Claude writes two kinds of prose. A **Pick Note** explains one pick. The
**Draft Summary** reviews the whole draft and the deck built from it.

### 1. Which picks earn a Pick Note

A **Noted Pick** is one whose verdict is `questionable` or `mistake`, or
that is a **Narrow Pick**. A Narrow Pick is one where:

- the pack held at least `narrow_pick_min_cards` = 8 distinct cards,
- exactly one of them was `solid`,
- at least `narrow_pick_min_questionable` = 2 of them were `questionable`,
- and the drafter took the `solid` card.

Critical notes explain what the pick cost. Narrow Pick notes give credit
for finding the one right answer when close alternatives were tempting.
Both thresholds are placeholders in `FitnessConfig`. The questionable
condition is there to exclude "one bomb and chaff" packs: HOB has six packs
with a single `solid` card, and none of them has two `questionable` ones,
so HOB gets three notes, all critical. A draft with no notes is still a
valid outcome.

This replaces ADR 0008 §3's "only a `mistake` earns a note". The bands
themselves are unchanged.

### 2. A Pick Note only knows the moment of the pick

A Pick Note uses only what was true when the pick was made: the pack, the
pool before it, and the scores. Nothing from later in the draft, so no
wheels and no final pool. A practice draft's live note and a Draft Review's
note on the same pick are therefore the same note, and a note never
changes once shown (ADR 0020). Hindsight, such as what wheeled and what the
pool became, belongs in the Draft Summary.

### 3. When notes are written

- **Imported drafts** (17Lands links): the Python verdicts appear at once,
  with a speech-bubble marker on each Noted Pick. A note is written the
  first time its pick is opened, then stored. An anonymous visitor sees the
  marker, and opening it says "Sign in for a coach's note on this pick".
- **Practice drafts**: notes are written live. The control that advances to
  the next pick stays disabled until the note arrives. After one automatic
  retry, or `pick_note_timeout` = 15 seconds, it unlocks, and the pick
  shows "note unavailable" with a retry button. Picks without a note never
  wait. A redraft pick with the same pack, pool and choice as its source
  reuses the stored note.
- **The Draft Summary** runs only once a deck has been submitted (ADR 0025),
  for both kinds of draft.

### 4. Models

| Call | Model | Effort | Calls |
|---|---|---|---|
| Pick Note | Claude Haiku 5.5 (`claude-haiku-5-5`) | `low` | one per note |
| Draft Summary | Claude Sonnet 5.5 (`claude-sonnet-5-5`) | `low` | one per draft |

One call per note, in both features, so a note reads the same wherever it
was written, and there is one prompt to version and evaluate rather than
two. The eval harness may show Haiku can write the summary too; if so,
switch.

### 5. The brief

A pure module, `briefing/`, turns a `DraftAnalysis` and a mapping of card
facts into the brief. A thin I/O function loads the card facts (name, mana
cost, rarity, type line, oracle text) for exactly the cards in the
analysis. The brief, not `DraftAnalysis`, is the contract the
invented-statistic check runs against.

- **Every number is pre-formatted by Python as display text** ("57.3%",
  "+2.4pp", "pick 9", "1,204 games"), and the prompt says to quote numbers
  exactly as given. The eval then needs only an exact string match. Any
  comparison Claude might want to make, such as the gap between two cards,
  is computed and put in the brief.
- **Oracle text is included only for the card taken and the best card**,
  and for a Narrow Pick also the next two cards below it. Every other card
  gets its name, cost, rarity and type line.
- **The format primer** (archetype win rates, top commons, speed), built
  from `archetype_stats`, goes in the Draft Summary call only. Pick Notes
  are about the pick.

### 6. Prompt caching

Each call is laid out with everything shared between calls first and the
data last:

| Call | Cached block 1 | Cached block 2 | Not cached |
|---|---|---|---|
| Pick Note | instructions, vocabulary, few-shot examples | none | this pick's brief |
| Draft Summary | instructions, vocabulary, few-shot examples | the set's format primer | this draft's facts and deck |

Cache entries use the **1-hour lifetime**. Writing one costs 2× the input
price against 1.25× for the 5-minute default, but imported-draft notes are
written on click, so at low traffic a 5-minute entry would often expire
between calls. Both models' minimum cacheable prefix is 512 tokens; the
instructions with their few-shot examples will be about 1.5–2k. Nothing
user-specific, no timestamp and no unsorted JSON goes into a cached block,
and a test asserts the cached blocks are byte-identical across two
different drafts. `llm_calls` records cache-read and cache-write tokens on
every call, so the lifetime can be revisited from data.

### 7. Structured output

Responses use structured outputs (`messages.parse()` against a Pydantic
model), keyed by pack and pick. Claude writes prose fields only. Python
attaches the verdict, gap and best card when it renders, so the prose can
never contradict the label. On a validation failure the call is retried
once, then fails cleanly, and the Python-only review still shows. Sonnet
5.5 calls use the API's server-side refusal fallback.

### 8. Where prose is stored

- **`llm_calls`** (Phase 4a): one row per call, with model, prompt
  version, purpose (`pick_note` or `draft_summary`), input, cache-read,
  cache-write and output tokens, cost, latency, status and `user_id`.
  `user_id` is nullable **only** for eval and CLI runs. Every call made
  for a user has one (ADR 0021).
- **Practice drafts**: each Pick Note and its prompt version are stored
  next to its pick in the practice draft's document. This amends ADR 0020
  §5.
- **`draft_reviews`** (Phases 5–6): the notes and the Draft Summary for an
  imported draft, with the Reviewed Deck and the current deck (ADR 0025).

### 9. Prompts and evaluation

Prompts are versioned files, `docs/prompts/pick_note.v1.md` and
`docs/prompts/draft_summary.v1.md`, never edited in place. Each holds
about three few-shot examples written by Jackson, so the tone is his
(Claude drafts candidates from real picks for him to rewrite). The eval
harness runs the noted picks from HOB and a second draft. It asserts the
JSON validates, every number in the output appears in the brief, and notes
stay under their length cap.

## Considered options

- **A note for every pick** (§4.2 as planned) was rejected. It contradicts
  ADR 0008's point that a few notes land harder than forty.
- **Mistakes only** (ADR 0008 as written) was rejected. It leaves a
  well-drafted pool with no prose and gives no credit for hard right
  answers.
- **One batched call for an imported draft's notes** was rejected so the
  two features share one note prompt.
- **Pick Notes that use hindsight in Draft Review** were rejected. They
  would make a practice draft's notes differ from its review's notes.
- **Raw floats in the brief, with a rounding-tolerant eval**, were rejected
  as too loose to catch a real invented number.
- **A fake tool whose input schema is the output** was rejected, because
  structured outputs are now first-class, and forced tool choice returns
  an error on Claude Sonnet 5.5.

## Consequences

- A Draft Review costs far less than the plan's $0.05–0.15. A Pick Note is
  about 1k tokens of brief plus the cached block, around $0.0003 on Haiku.
  The Draft Summary is about 3–5k tokens on Sonnet.
- A practice draft can pause for a few seconds on a Noted Pick. That is the
  price of feedback before the next decision.
- Phase 4 gains Narrow Pick detection in `analysis/` and a new `briefing/`
  module.

**Revisit when:** Narrow Picks read as cheap or never fire on real drafts
(tune the two thresholds); the eval shows Haiku can write the Draft
Summary; or `llm_calls` shows the 1-hour cache is rarely read before it
expires.

**Glossary:** Pick Note, Noted Pick (replacing Relevant Pick), Narrow Pick
and Draft Summary are added to `CONTEXT.md`.
