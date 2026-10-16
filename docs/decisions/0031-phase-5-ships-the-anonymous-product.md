# ADR 0031 — Phase 5 ships the anonymous product, with Claude behind an admin key

**Status:** Proposed · **Date:** 2026-10-16 · **Amends:** ADR 0021 (who may call Claude, until Phase 6), ADR 0024 §8 (`llm_calls.user_id`, `draft_reviews`), development plan Phase 5 (`log_text`, `review_jobs`, polling) · **Relates to:** ADR 0023 (single-draft replays), ADR 0025 (the Submitted Deck), ADR 0027 (limits)

---

## Context

Phase 5 (Draft Review end to end) comes before Phase 6 (accounts), but
ADR 0021 says Claude is only called for a signed-in user. The Phase 5 text
also predates later decisions: it still lists pasted Arena log text as an
input and plans a 10–20 second review run as a background job with polling.
Neither holds any more. Verdicts are Python only, a Pick Note is one Haiku
call, and the Draft Summary is one Sonnet call after a deck is submitted.

## Decision

### 1. Phase 5's public product is the anonymous tier

Verdicts, fitness scores, Noted Pick markers, the deck builder and Deck
Ratings. No account is needed and no review is saved. Where Claude's prose
would appear, the page says "Sign in for a coach's note" (Pick Notes) or
"Sign in for a Draft Summary".

### 2. Claude endpoints exist, behind an Admin Key

The lazy Pick Note endpoint and the Draft Summary (run on the first deck
submission) are built and tested in Phase 5. They require an `X-Admin-Key`
header matching an environment variable on Render. This lets the full
pipeline run on the live site and doubles as the admin gate of issue #32.
Phase 6 replaces "valid admin key" with "signed-in user" in the same
dependency, leaving the endpoint logic alone.

`llm_calls.user_id` is null for **CLI, eval and admin-key calls**, and for
no other call. This amends ADR 0024 §8.

### 3. The input is a 17Lands link only

`POST /api/drafts` takes a 17Lands URL or draft ID. The plan's
`source: "log_text"` and its "pasted MTGA log works identically" check are
removed. The Arena `Player.log` is a post-launch input (CLAUDE.md).

### 4. No job layer

Verdict computation, a Pick Note and the Draft Summary are each a plain
request that waits for its result, with a loading state in the UI. The plan's
`review_jobs` table, `BackgroundTasks` and 1.5 s polling are dropped. If the
Draft Summary's measured latency proves 30 s or more, it streams; it still
does not become a job.

### 5. Storage

- **`drafts`** (new): the parsed `DraftLog` as JSONB, keyed by the 17Lands
  draft id. A **Replay Cache**: public data, no user, no review. It
  fulfils ADR 0023's "one fetch per draft".
- **Verdicts are never stored.** Every `GET` recomputes them from the
  cached log and the current statistics.
- **`draft_reviews`** (new): Pick Notes, the Draft Summary, `reviewed_deck`,
  `current_deck` and prompt versions. In Phase 5 only admin-key calls write
  to it, so `user_id` is nullable for now. The Phase 6 migration deletes
  those rows and makes it `NOT NULL` (ADR 0021).
- Each stored note carries the stats snapshot id it was written against. If
  today's statistics differ, the page tags it "written against older stats".
  Pinning verdicts to a snapshot stays a practice-draft rule (ADR 0020).
- Anonymous deck submissions are not stored. The client sends the 40 cards
  and gets Deck Ratings back.

### 6. Limits without users

- Submitting a draft link (the 17Lands fetch) is limited per IP, a few a
  minute and a few dozen a day. A Replay Cache hit costs 17Lands nothing and
  does not count.
- Deck submissions are limited per IP.
- Admin-key calls have no allowance, but the daily spending cap (ADR 0027
  §3) applies to every Claude call.
- The counter lives in Postgres, not memory, because Render instances
  restart. The numbers are config values, tuned in Phase 8.

### 7. The review page

- A read-only, shareable URL at `/draft/<17lands id>`. It never shows
  admin-written prose.
- A plain skeleton for the fast Python call. Fake step-by-step progress is
  not shown, since there is no job to report on.
- The deck builder is a standalone Svelte component (pool in, 40 cards out),
  so Phase 7 reuses it with a practice draft's pool.
- Card images load only when a pick is expanded.
- The 17Lands credit (ADR 0002 §4) is on every review.

### 8. Build order

One session and PR each:

- **5a** import and verdicts API: `drafts` migration, `POST`/`GET
  /api/drafts`, the limiter, the 17Lands error states.
- **5b** the review page.
- **5c** the deck builder and the Deck Ratings endpoint.
- **5d** the admin-gated Claude endpoints, the `draft_reviews` migration,
  latency and token counts added to eval reports, and the plan's cost and
  timing figures re-derived from `llm_calls`.

Each migration is confirmed with Jackson before it is written.

## Considered options

- **Python-only until Phase 6** was rejected. The Claude endpoints would
  then be untested in production until accounts exist, and Phase 6 would
  carry both auth and the first live Claude calls.
- **Phase 6 before Phase 5** was rejected. 5a–5c make a complete product
  without accounts, and accounts can wait for something worth signing in to.
- **Keep the job table and polling** was rejected as machinery for a delay
  that no longer exists.
- **Store verdicts, or pin them to a snapshot** was rejected for imports:
  recomputing is cheap and the nightly drift is small.

## Consequences

- Phase 6 is smaller: swap one dependency, add `NOT NULL`, add ownership.
- Until Phase 6, only the site owner sees Claude's prose live.
- A stored note can briefly disagree with a recomputed verdict. The
  "older stats" tag is the mitigation.

**Revisit when:** Phase 6 lands, or the Draft Summary's latency is measured.

**Glossary:** Admin Key and Replay Cache are added to `CONTEXT.md`.
