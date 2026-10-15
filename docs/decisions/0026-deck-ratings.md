# ADR 0026 — Deck Ratings fitted to the game dump

**Status:** Proposed · **Date:** 2026-10-15 · **Relates to:** ADR 0010 and 0013 (curve targets), ADR 0017 (synergy), ADR 0025 (the Submitted Deck)

---

## Context

Every Submitted Deck gets an overall rating and a rating for each metric,
computed in Python, with no Claude call. They are shown to anonymous
visitors too, and they are the facts the Draft Summary explains. Grades
set by hand ("16 creatures is a B") would be invented tunables. The 17Lands
game dump we already ingest has a `deck_<card>` column on every row, next
to the game's result, so every format comes with a large set of real decks
and how they did.

## Decision

### 1. The metrics

All are computed in pure `analysis/` on the 40-card deck:

| Metric | Measure |
|---|---|
| Card quality | Mean GIH WR of the nonland cards, against the format average |
| Curve | Nonland cards by mana value, against the format targets of ADR 0010/0013 |
| Synergy | Tag-pair firings among the deck's own cards (ADR 0006, 0017) |
| Creatures and removal | Counts, as in `PoolState` |
| Mana | Colour Sources for each colour against the pip requirements of the deck's spells |
| Notable omission | At most one: the best sideboard card playable in the deck's colours, if it outscores the deck's weakest playable by more than `mistake_gap` |

**Mana** compares Colour Sources against **Frank Karsten's published
40-card tables**: the sources needed to cast a C, CC or CCC spell on curve
reliably. A deck that skimps on sources for a pip-heavy bomb is called out
for it. The table values are taken from Karsten's published source and
cited, not reproduced from memory. A Colour Source is a land that produces
the colour, or a card tagged as a **Fixer** for it. Fixer tags are
authored by hand per set; how fixers count (a Treasure maker against a
mana creature, for example) is to be designed before Phase 4b builds it.

### 2. The ratings

- **Each metric rating** is the deck's percentile on that metric among the
  format's 40-card decks in the game dump, shown as a letter grade from A
  to F, with bands at fixed percentiles.
- **The overall rating** comes from a logistic regression of game win on
  the metrics, fitted per format. It predicts a win rate, and that is
  graded on the same percentile bands.
- The fit runs offline, in the nightly ingest. Each format's coefficients
  and percentile tables are stored in a new table, and a practice draft
  rates against its Stats Snapshot (ADR 0020).
- A format with no game dump (FRA today) shows "not enough data to rate"
  for each grade.

The fit uses only 40-card decks, to match the Submitted Deck.

## Considered options

- **An overall grade that averages the metric grades** was rejected. It
  weights every metric equally, and the regression shows which metrics
  actually predict wins in a format.
- **Thresholds set by hand** were rejected under the "derive tunables from
  data" rule.
- **Requirements derived from the dump** were rejected in favour of
  Karsten's tables. They are the established answer to this exact question,
  and the dump still decides how much a shortfall matters through the mana
  metric's own grade.

## Consequences

- **The grades are relative to 17Lands users,** who play better than
  average. A "C" is average among 17Lands decks, and the UI must say so.
- This is the largest new piece of Phase 4: deck metrics, a fitting job in
  the ingest and a new table. It needs confirming as a schema change when
  built.
- Sets need Fixer tags before their mana ratings are complete.

**Revisit when:** the regression's coefficients come out unstable or
counter-intuitive on a format; or a pip-heavy deck is graded well on mana
despite too few sources.

**Glossary:** Deck Rating, Colour Source and Fixer are added to
`CONTEXT.md`.
