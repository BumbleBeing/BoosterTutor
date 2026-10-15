# ADR 0027 — Rate limits and the daily spending cap

**Status:** Proposed · **Date:** 2026-10-15 · **Amends:** development plan §4.4 item 3 (10 reviews a day) · **Relates to:** ADR 0021 (no account, no Claude), ADR 0024 (Pick Notes and the Draft Summary)

---

## Context

A Draft Review is no longer a single call. An imported draft writes its
Pick Notes one at a time as they are opened, a practice draft writes them
live, and the Draft Summary waits for a submitted deck (ADR 0024, 0025).
A per-call limit would make users ration clicks. A per-user limit also
does nothing against a bug that loops, or many accounts made to farm
calls.

## Decision

### 1. A draft is the unit

A draft counts against its user's allowance **once, at its first Claude
call**. Every Pick Note and the Draft Summary for that draft are then free.
A redraft is a new draft and counts again.

### 2. The daily allowance

`drafts_per_day` = 10 per user, a placeholder. It is enforced in the
backend, not the UI.

### 3. The daily spending cap

A global kill switch reads today's spend from `llm_calls`. Once it is over
`daily_spend_cap` (about $5 a day while the app is small), no further
Claude calls are made that day. Users see "The coach has retired for the
day, please come back tomorrow." in place of the prose.

### 4. Without credits, the product still works

A signed-in user who has used up their allowance, or who hits the cap,
still gets every Claude-free feature, exactly as an anonymous visitor
would: verdicts, fitness scores, Noted Pick markers, the deck builder and
Deck Ratings.

## Considered options

- **A limit per call or per note** was rejected. It would make users
  ration which picks they open.
- **No global cap** was rejected. It is the guard a first production app on
  a pay-per-use API most needs, and it costs little once `llm_calls`
  exists.

## Consequences

- The cap and `llm_calls` are built together, in Phase 4a, before any
  user can reach Claude.
- A heavy day can cut coaching short for everyone. The Python review
  carries on regardless.

**Revisit when:** paying users arrive. Selling extra reviews per day is a
possible source of revenue in a later release. Or revisit when the cap is
hit often enough to show it has been set too low.
