# ADR 0020 — Practice drafts: bot picks, stats snapshots and redrafts

**Status:** Proposed · **Date:** 2026-10-13 · **Relates to:** ADR 0008 (fitness classes, which bots pick from), ADR 0013 (format-level constants), ADR 0019 (opening packs, pinned here by index)

---

## Context

A practice draft seats the user with seven bots and rates each of the
user's picks as it is made. Three requirements pull against the obvious
implementation:

1. **Bots should feel like drafters, not like the grader.** The fitness
   function both runs the bots and grades the user. If bots always took the
   top card, every blind spot in the function would become a blind spot of
   every bot at the table, and the bots would read as mechanically perfect.
2. **A verdict, once shown, never changes.** The 17Lands statistics refresh
   nightly, and the fitness constants change with each ADR. If a draft were
   recomputed from "seed + picks", what the user was told at pick 7 would
   drift under them.
3. **A redraft is a controlled experiment.** Replaying a draft from pick 1,
   the user should be able to change one pick and see only the consequences
   of that change. Bots whose packs did not change must repeat their
   original picks exactly, and the new picks must be rated with the original
   figures.

## Decision

### 1. Bots pick mostly `solid`, sometimes `questionable`, never `mistake`

Each bot scores the pack against **its own pool** and classes every card as
ADR 0008 defines. Then:

- With probability `bot_questionable_rate`, and only if the pack holds at
  least one `questionable` card, the bot takes a `questionable` card,
  uniformly at random.
- Otherwise it takes a `solid` card, uniformly at random. A `solid` card
  always exists, since the best card in any pack is `solid`.
- A bot never takes a `mistake`.

`bot_questionable_rate` must lie between **0.10 and 0.20**. The prototype
starts at a placeholder of 0.15. The final value is read off the data: the
share of 17Lands human picks that were `questionable`, among picks where a
`questionable` card was available, clamped to that band. The three
reference drafts in ADR 0018 had 2, 5 and 8 `questionable` verdicts out of
42 (5–19%), so the band is plausible before measuring.

Taking `questionable` cards is what keeps bots from looking mechanically
perfect. Uniform choice within a class keeps every pick defensible under the
grader while varying the table from draft to draft. Mistakes are excluded
because a bot that blunders sends signals the user cannot learn from.

### 2. Each seat has its own random stream for each pick

Every random draw a bot makes is seeded from `(draft seed, seat, pick)`. A
bot's choice at one pick therefore depends only on its own pack, its own
pool and that seed. It does not depend on how many random numbers other
bots consumed. A single shared stream would let one extra draw at one seat
shift every later pick at every seat.

Each stream draws in a fixed order: first the class coin (`questionable` or
`solid`), then the card within the class.

### 3. In a redraft, bots keep their original pick whenever they can

The class coin comes from the stream, so it lands the same way as in the
original. If a bot's pack has changed:

- If its original card is still in the pack, and still in the class the coin
  chose for its pool, it takes that card again.
- Otherwise it draws uniformly within that class, falling back to `solid`
  when the class is empty.

A bot whose pack has not changed makes exactly its original pick. A change
spreads only as far around the table as the changed cards actually travel.

### 4. Every practice draft is pinned to a stats snapshot

A **stats snapshot** freezes everything that rates a pick: card draft
statistics, card archetype statistics, archetype statistics, the tag
taxonomy and its coefficients, the synergy baseline, `FitnessConfig` and
`bot_questionable_rate`. Snapshots are stored once, in a shared
content-addressed table, so identical nightly refreshes deduplicate. A
snapshot is kept while any draft refers to it.

A new practice draft uses the latest snapshot. A redraft uses its root
draft's snapshot, which includes any new picks after the user diverges.

**A snapshot pins data, not code.** Each draft also records the version of
the fitness code that rated it. A redraft made after the code has changed
runs the old snapshot through the current code, and is labelled as rated by
a newer grader. Keeping every past version of the fitness function runnable
forever was rejected as too heavy for one maintainer. Redrafting across a
code change was not blocked either, because the stored bot picks still
replay until the user diverges.

### 5. What is stored

One JSONB document per practice draft, using small integer card IDs:

- the set, snapshot ID, code version and seed
- the 24 opening pack indices (ADR 0019)
- every pick at every seat: 8 × 42
- for the user's seat, every pack exactly as shown, each card's fitness and
  fitness class, and the pick's verdict

Nothing that was shown is recomputed afterwards. The document is shaped like
a parsed 17Lands draft, so Draft Review runs on it unchanged, and Deck
Review can be added later without a migration.

### 6. Redrafts form a tree

A redraft points to the draft it was made from, and the original practice
draft is the root. A redraft can itself be redrafted down to depth 5,
counting the original as depth 0. On a depth-5 draft the Redraft action is
disabled. There is no limit on breadth. Deleting a draft deletes its whole
subtree, after a confirmation that gives the count.

## Consequences

**Storage is small.** A draft is about 8 KB raw and 3–4 KB after Postgres
compresses the JSONB, so 10,000 drafts come to about 40 MB. Snapshots are
about 25 KB compressed per set per refresh, at most about 9 MB per set per
year. One row per card would have been about 650 rows per draft, with
nothing gained.

**The grader is also the environment.** Bots and verdicts share one
function, so a practice table is internally consistent but can't reveal a
blind spot of that function. The `questionable` share softens this, and it
is why bot realism is measured against human data (archetype mix,
deckability, and when cards leave the pack compared with ALSA), not against
the grader.

**Draft Review on a practice draft uses the stored snapshot,** not today's
figures, so its written critique agrees with the borders the user saw.

**Revisit when:** bot realism measurements disagree with 17Lands in a way
`bot_questionable_rate` cannot fix; or rewinding to an arbitrary pick is
wanted. That needs no storage change: rewinding to pick N is a redraft with
the first N − 1 user picks forced.
