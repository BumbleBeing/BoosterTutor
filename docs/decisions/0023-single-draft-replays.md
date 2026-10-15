# ADR 0023 — A single draft's replay is fetched from 17Lands when its owner asks

**Status:** Proposed · **Date:** 2026-10-14 · **Amends:** ADR 0002 §1 ("the endpoints behind 17lands.com are not called") and CLAUDE.md's 17Lands rule ("never called from a user request path"), for this one case only · **Relates to:** development plan §3.1 (input 1), ADR 0021 (nothing anonymous is stored)

---

## Context

Draft Review's first input is a link to the user's draft on 17Lands. The
pick-by-pick log behind that link comes from the 17Lands website's own
backend, not the public datasets:

```
GET https://www.17lands.com/data/draft?draft_id=<id>           # every pack and pick
GET https://www.17lands.com/data/event_metadata?draft_id=<id>  # set, format, record
```

DraftDouble confirmed both on 2026-09-18 (its `docs/data-sources.md` §8). No
login is needed; the 32-character draft ID is the only gate, as it is for
the shareable link. An unknown ID answers `404` with a JSON message.

ADR 0002 rules out every 17lands.com endpoint, and CLAUDE.md says 17Lands is
never called from a user request path. Both were written about the
**aggregate** statistics (card and colour ratings), which 17Lands restricts
to its own site and publishes instead as the public datasets. A single
draft's replay is a different kind of data. It is one user's own draft, the
public datasets do not contain it (they are anonymised, with no draft IDs a
user could look up), and it can only be fetched at the moment the user
hands us the link.

## Decision

**When a user submits a 17Lands draft link or ID, the backend fetches that
one draft's replay and event metadata from 17lands.com.** This is the only
17lands.com request BoosterTutor makes. Every statistic still comes from
the public datasets (ADR 0002).

The limits that keep it polite:

- **Only on a user's explicit submission.** Never in bulk, never on a
  schedule, never to discover drafts, never for an ID the user did not give.
- **One fetch per draft.** A draft that has finished never changes, so the
  parsed log is kept and a second review of the same draft does not fetch
  again. Where it is kept is settled with Draft Review's storage (Phase 5),
  within ADR 0021: an anonymous review stores no review, so at most the
  parsed log is cached, keyed by draft ID.
- **A per-user (or per-IP, when anonymous) rate limit**, so BoosterTutor can
  never be used as a proxy to pull 17Lands' drafts in volume. The limit is
  set in Phase 8 (hardening).
- The same identifying `User-Agent` as the ingests, a short timeout, and no
  retry on a `4xx`. A failure is shown to the user as a clear message
  ("that draft is private or not found", "17Lands didn't answer"), never
  retried in a loop.
- The visible 17Lands credit of ADR 0002 §4 appears on every review.

## Considered options

- **Only the Arena `Player.log` and MTGO inputs, no link**: rejected. The
  link is the input most users already have, since 17Lands' tracker is
  what they draft with, and pasting a log is a much harder first step.
- **Email 17Lands first and wait for an answer**: not made a precondition.
  The use is small and user-initiated, and it is the same request the user's
  own browser makes when they open the link. If 17Lands objects, this ADR is
  withdrawn (below).
- **Fetch from the browser instead of the backend**: rejected. 17Lands does
  not offer cross-origin access, and parsing and grading belong in Python
  anyway.

## Consequences

- CLAUDE.md's 17Lands rule gains this one named exception, and ADR 0002 §1
  points here.
- The endpoint is undocumented and may change without notice. The parser
  fails with an "upstream" error on any unexpected shape rather than
  guessing, and its tests run against saved payloads.
- This is an accepted risk: the 17Lands usage guidelines discourage
  automated use of their API, and this endpoint has no published terms of
  its own.

**Revisit when:** 17Lands objects or publishes terms covering it; the
endpoint starts to carry the "only for use on 17Lands.com" notice or
requires a login; or 17Lands offers an official way to export a draft.
