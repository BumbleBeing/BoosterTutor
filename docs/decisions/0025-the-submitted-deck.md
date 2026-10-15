# ADR 0025 — The Submitted Deck: build a deck, then get the Draft Summary

**Status:** Proposed · **Date:** 2026-10-15 · **Amends:** ADR 0022 (part of Deck Review comes into v1), ADR 0021 (what an anonymous visitor gets) · **Relates to:** ADR 0024 (the Draft Summary), ADR 0026 (Deck Ratings)

---

## Context

A pick-by-pick review judges decisions, not the result. What a drafter
actually takes into games is the deck, and a 17Lands draft link carries no
decklist, only picks. ADR 0022 postponed Deck Review because it "needs its
own analysis engine (swap candidates, archetype detection, decklist
parsing)". A deck built in our own interface, from a known pool, needs none
of those expensive parts: there is nothing to parse, and the archetype is
already predicted.

## Decision

**After an imported draft is parsed, or a practice draft ends, the user
builds a deck from the pool in a deck-building component.** It sits below
the pick review, headed "Submit your final deck for a full Draft Review".
The Draft Summary (ADR 0024) critiques what is submitted.

### 1. The deck builder

- Only pool cards and basic lands can be used. Any basic lands drafted are
  pruned from the pool when the draft is parsed or the practice draft ends.
- Five buttons, stacked to the left of the builder, each add one basic land
  of one type.
- Double-clicking a basic removes it. Double-clicking any other card moves
  it between the deck and the sideboard, as in the practice draft's pool.
- A deck must be **exactly 40 cards** to submit, with a live count shown
  ("37 / 40"). Allowing larger decks would need every deck metric to handle
  them, for little gain.
- Submitting asks for confirmation: "Only your first deck gets a written
  review. Later decks get ratings only."

### 2. Only the first deck gets a review

A user may submit again, and each new **Submitted Deck** replaces the
current one. Only the first, the **Reviewed Deck**, gets the Draft
Summary. Later decks get the Python Deck Ratings (ADR 0026) only. The
saved review keeps both `reviewed_deck`, frozen at first submission, and
`current_deck`. The written review always describes the Reviewed Deck. The
ratings panel shows the current deck.

The submission is keyed per user and per draft. For an imported draft that
is `(user, 17Lands draft id)`, and resubmitting the same link shows the
existing review. Each practice draft and each redraft is its own draft.
Deleting a saved review does not restore the first submission: the row is
kept and marked deleted, so delete-and-resubmit is not a way round the
rule or the rate limit.

### 3. Signed in and anonymous

- **Signed in:** everything above.
- **Anonymous:** the builder works and shows the Deck Ratings, but there is
  no Draft Summary and nothing is saved, so the one-submission rule does
  not apply. This extends ADR 0021, whose anonymous Python-only review now
  includes deck ratings.

### 4. What stays postponed

Deck Review's **ranked swap suggestions** stay after launch, as does a
pasted decklist as an input. The Draft Summary may mention one omission,
but only as a fact Python computed (ADR 0026), never as a ranked list.

## Considered options

- **A Projected Deck computed by Python** (the 23 best playables in the
  predicted archetype) was rejected. The user's own deck is what they will
  play, and critiquing a deck they never built teaches less.
- **Full Deck Review in v1, swaps included,** was rejected as the scope
  creep ADR 0022 exists to stop.
- **Any deck of 40 cards or more** was rejected to keep the metrics simple.
- **A builder for signed-in users only** was rejected. Ratings cost no
  Claude call, and they show an anonymous visitor what an account adds.
- **One submission only, with no replacement** was rejected. Users will
  want to try other builds, and ratings are free to recompute.

## Consequences

- Phase 4b needs a `Deck` input shape and deck metrics (ADR 0026) before
  the Draft Summary prompt can be written (Phase 4c).
- The deck builder UI is built twice over: Phase 5 for imported drafts,
  Phase 7 for practice drafts. Both use one component.
- The HOB fixture needs a deck. Jackson builds the one he would have
  played, so the summary evals have a realistic input.

**Revisit when:** v1 has launched and Deck Review proper (swaps, pasted
lists) starts. It inherits this builder and these metrics.

**Glossary:** Submitted Deck and Reviewed Deck are added to `CONTEXT.md`.
