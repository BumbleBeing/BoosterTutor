# ADR 0022 — v1 is Draft Review and Practice Draft; Deck Review waits

**Status:** Proposed · **Date:** 2026-10-13 · **Amends:** the development plan's feature list, phase order and non-goals; ADR 0021 (whose anonymous Deck Review now arrives with Deck Review, after launch) · **Relates to:** ADRs 0019 and 0020 (Practice Draft's design)

---

## Context

The development plan launched with two features, Draft Review and Deck
Review, and placed Practice Draft in a Phase 10 after launch. Building the
Practice Draft prototype in DraftDouble (issues #42–#45) changed that
judgement. It already runs end to end against real HOB data, and it turns
the coach from something you consult after a draft into something you
practise with. That is the "learning by doing" the project wants to teach
through. Deck Review, meanwhile, has no prototype and needs its own
analysis engine (swap candidates, archetype detection, decklist parsing).

## Decision

**v1 launches with Draft Review and Practice Draft. Deck Review is
postponed until after launch,** not dropped. The phases become:

| # | Phase |
|---|---|
| 5 | Draft Review, end to end |
| 6 | Accounts and saved history (was 7) |
| 7 | Practice Draft, end to end (was 10) |
| 8 | Hardening |
| 9 | Launch |
| 10 | Deck Review, after launch (was 6, plus §3.4's deck analysis and §3.1's decklist inputs) |

Accounts move ahead of Practice Draft because practice drafts are saved per
account (ADR 0021): building them against a temporary local user first
would mean doing the storage twice.

## Considered options

- **Keep Deck Review in v1 and add Practice Draft as a third launch
  feature** was rejected: three features before launch is the scope creep
  the plan's non-goals exist to stop.
- **Drop Deck Review entirely** was rejected. Practice Draft's pool grid
  already splits a pool into a deck and a sideboard, and a practice draft's
  stored record has a parsed 17Lands draft's shape, so Deck Review has a
  natural input waiting for it. It is a strong follow-up, just not a launch
  requirement.
- **Practice Draft before accounts, with a temporary local user** was
  rejected for the storage reason above.

## Consequences

- Phase 3 no longer parses decklists and §3.4's deck analysis moves to
  Phase 10, so the analysis engine before launch is draft analysis only.
- The schema before launch has no `decks` or `deck_reviews`; it gains
  `stats_snapshots` and `practice_drafts` instead (Phase 7).
- Without an account, the only v1 feature available is Draft Review, as
  Python output (ADR 0021). Practice Draft needs an account.
- The plan's "Phases 5 and 6 each end with something you can show someone"
  becomes Phases 5 and 7.

**Revisit when:** v1 has launched; Deck Review is then the next phase.
