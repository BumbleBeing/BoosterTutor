# ADR 0017 — Synergy measures a margin, not a level

**Status:** Proposed · **Date:** 2026-10-12 · **Supersedes:** ADR 0006 §5's absolute formulation of the synergy total (the edge walk, the authored-pairs-only rule and ADR 0009's decay are all unchanged) · **Relates to:** ADR 0003 §3 (the backtest, now built), ADR 0013 §4 (the transcribe-by-hand rule, knowingly broken here)

---

## Context

The backtest over the full HOB dump — 43,650 drafts, 1,639,501 scorable
picks — wanted **`synergy_weight = 0.0`**, at 38.8% leverage. The data was
not failing to see the term; it was seeing it clearly and asking for it to be
switched off.

The reason is double-counting, and it is measurable. A card's GIH WR is
observed over the real decks that played it, so it already prices the card's
*typical* synergy:

| | n | mean GIH WR |
|---|---|---|
| on at least one authored edge | 144 | 55.58 |
| on none | 44 | 53.15 |

**+2.42pp** of the win rate is already "this card is a synergy piece". The
term then paid again for every complement in the pool — including the ones
an average deck would also have, which the 55.58 already assumed. The same
pattern explains the rest of the fit: creatures carry +2.88pp and
`creature_weight` fitted to 0.0; `_removal_` cards carry +2.33pp and
`removal_weight` fell from 1.25 to 0.5. Mana value is the one thing GIH WR
knows nothing about, and `curve_weight` is the one deck-shape term that
survived.

The organising principle: **a term earns its place only if it encodes
something the card's win rate cannot already contain.**

## Decision

Score synergy as a margin against what the card usually finds:

```
firing = coefficient × ( n_eff(n, decay) − E[n_eff | card, pack, edge, end] )
```

A typical pool pays nothing, an unusually rich one pays a bonus, and one
missing the complement entirely pays a **penalty**. `synergy_weight` moves
from 1.0 to **0.75**.

**Signed, not clamped.** Tested both: clamping at zero gave a holdout loss of
1.3879 against 1.3833 signed. Having none of a card's complements is genuine
bad news and the absolute form could never say so. 60% of live firings are
now negative, which is the distribution's natural shape — most pools are
slightly below average for most cards, with a long right tail where a pool is
really built around something.

### The baseline is a stored histogram, not a stored expectation

A new `synergy_baseline` table holds, per (card, pack number, edge, end), the
**count of observations at each complement count `n`**, with the `n = 0` rows
included. `E[n_eff]` is computed from it at load, using whatever decay the
edge currently carries.

Storing counts rather than the expectation is the decision worth recording.
The expensive input is pool composition across 1.6M picks, and it depends on
no weight at all. A stored expectation would go stale the moment a
coefficient or decay was nudged in the tagger — and 11 of 16 edges were
re-tuned in a single sitting — forcing a re-measurement each time. A
histogram never goes stale. It also makes fitting the per-edge coefficients
and decays possible later with no further schema change.

For HOB: **8,537 rows over 1,170 (card, pack, edge, end) cells, 144 cards**,
derived in 62 seconds.

Two traps, both now pinned by tests. The expectation must average over
**every appearance** of the card, not only the ones where the edge fired —
averaging over firings alone yields the expectation conditional on firing,
and then every pool looks poor. And an edge that does **not** fire still
contributes `−E[n_eff]`, so the walk cannot skip zero counts.

### Keyed by pack number

Pools grow, so a card seen in pack 3 naturally finds more complements than
the same card in pack 1. Three buckets keeps the per-cell sample large while
removing most of that confound. Finer conditioning (on pool size) was not
tested and would thin the cells.

### `scripts/derive_synergy_baseline.py` writes to the database

Every other derived number in this project is printed for a person to
transcribe (ADR 0013 §4). That rule exists to stop a job clobbering a
*hand-picked* value; these are 8,537 measured rows that nobody will ever
author. An empty table is a supported state: the term then reverts to ADR
0006's absolute form exactly.

## Consequences

**Good.** The term is validated rather than assumed, and it is the first
constant in this project fitted rather than guessed. Measured on 132,246
picks and checked on a 487,198-pick holdout:

| | absolute | marginal, signed |
|---|---|---|
| `synergy_weight` | **0.0** | **0.75** |
| holdout pick-agreement loss | 1.3921pp | **1.3833pp** |
| holdout top-1 agreement | 51.86% | **52.32%** |
| outcome correlation (target 2) | −0.1284 | **−0.1294** |

**Both targets agree**, which had not happened before: pick agreement
improves on data the fit never saw *and* the outcome correlation strengthens
slightly, so this is not the imitate-rather-than-win trap that every earlier
result had to be hedged against. It also survives a joint re-fit — all twelve
other constants land identically.

**Costs.** The gain is modest: 0.0088pp of holdout loss, about 11% of
everything the whole fit achieved. The term's realised range collapses from
+0.00…+2.68pp to −0.69…+0.80pp on the reference drafts, so it is now a
tiebreaker between near-equal cards rather than something that reorders a
pack — which is the honest description of a signal worth 0.1pp at the median.

It only touches the **144 of 193 cards** that sit on an authored edge; for the
other 49 the margin is identically zero. That is a taxonomy-coverage fact, not
a property of the design, and it caps what this term can ever do.

`synergy_cap` (5.0) no longer binds in practice and has no floor on the
negative side, which is harmless while expectations are small (median 0.438)
but is not a guarantee.

**Observed** on the three reference drafts: WR unchanged at 30/7/1/4, BR
35/2/0/5 → 34/3/0/5, UG 22/11/3/6 → 23/9/4/6. The term fires on 611 of 882
scored cards rather than 357.

**Revisit when:** the per-edge coefficients are fitted (the next step, and the
reason the baseline stores counts); or if the taxonomy grows enough that the
49 untouched cards shrink; or if `top_firings` should surface the *worst*
firing as well as the best, which is a brief question (BoosterTutor #22) and
deliberately not settled here.
