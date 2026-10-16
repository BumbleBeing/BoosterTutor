# ADR 0029 — v1 launches with HOB only

**Status:** Accepted · **Date:** 2026-10-15 · **Relates to:** ADR 0013 (format constants), ADR 0022 (v1's scope), ADR 0026 and 0028 (Deck Ratings and land targets)

---

## Context

A format can be reviewed only once it has everything the analysis reads:
statistics, a hand-transcribed `format_constants` row (ADR 0013), a tag
taxonomy with its Fixers (ADR 0028), a synergy baseline (ADR 0017) and
Deck Ratings fitted from its game dump (ADR 0026). HOB has all of them.
MSH has statistics and a game dump but no `format_constants` row, no
taxonomy and no Fixers. FRA has no public game dump yet. The development
plan's Phase 4 checklist asked for Deck Ratings fitted for HOB and MSH.

## Decision

**v1 launches with one format: HOB Premier Draft.** MSH and FRA are added
after launch, together.

- The Phase 4 checklist asks for Deck Ratings fitted for HOB only.
- A draft from any other set is refused as an unsupported set (Phase 5's
  error handling), not analysed with missing inputs.
- The nightly ingest keeps loading cards and statistics for every recent
  draftable set, MSH and FRA included. It is cheap, and it keeps their
  data current for when they are added.

## Consequences

- Adding a format after launch is a checklist: its `format_constants`
  row, land targets included (`scripts/derive_land_targets.py`); its
  taxonomy and `mana_sources`; `ingest synergy-baseline`; and
  `ingest deck-ratings`.
- Until then, `ingest deck-ratings` skips MSH, and records why in
  `ingest_runs`, because MSH has no `format_constants` row.

**Revisit when:** v1 has launched.
