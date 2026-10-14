# ADR 0018 — Retiring openness, and the creature branch of role

**Status:** Proposed · **Date:** 2026-10-12 · **Supersedes:** ADR 0014 and ADR 0016 in full (the openness term is withdrawn, not revised); ADR 0003 §1.4's two-branch role term and ADR 0003 §1.5's openness term; ADR 0010's `target_creatures` · **Relates to:** ADR 0017 (the principle this applies), ADR 0013 (format-level constants), ADR 0012 §4 (`replacement_offset`, now unread), ADR 0007 §6 (openness's replacement gate, retired with it)

---

## Context

ADR 0017 named the organising principle while fixing synergy:

> a term earns its place only if it encodes something the card's win rate
> cannot already contain.

The same full-dump backtest — 43,650 drafts, 132,246 fit picks, a
487,198-pick holdout — zeroed two more weights and moved four constants.
This ADR applies the principle to the rest of the fit rather than leaving
measured zeroes sitting in `FitnessConfig` as though they were guesses.

| constant | was | fitted | leverage (fitted) |
|---|---|---|---|
| `openness_best_rate` | 0.5 | **0.0** | 6.0% |
| `creature_weight` | 0.40 | **0.0** | 20.7% |
| `ramp_start` | 4 | **0** | 23.0% |
| `ramp_span` | 10 | **14** | 23.2% |
| `curve_weight` | 0.75 | **0.25** | 30.4% |
| `removal_weight` | 1.25 | **0.5** | 13.1% |

`tax_value` (6.0, 43.5% leverage and the widest loss range in the run) and
`synergy_weight` (0.75, 46.1%) were confirmed unchanged.

## Decision

### 1. Openness is withdrawn, not tuned to zero

`openness_best_rate = 0.0` makes the entire term inert, so leaving it as a
constant edit would ship dead code pretending to be a design. The term, its
two constants, `openness_rate`, `pack_weight`, `Stats.alsa` and
`replacement_offset` (whose only remaining reader it was, since ADR 0012
removed the colour term's replacement floor) are all deleted.

This is the fifth independent signal against the term, and the first that
measures it on more than three drafts:

- ADR 0014 rewrote it after the original paid every late card the same rate.
- ADR 0016 confined it to pack 1, halving what it could ever touch.
- It can reach at most 14 of 42 picks, and only cards above replacement.
- On the three reference drafts it is non-zero on **4, 9 and 5** cards out
  of roughly 295 each, with a largest observed value anywhere of **0.78pp**
  against a `solid_gap` of 2.0. It has never once changed a verdict.
- The fit, with 132,246 picks to look at, set its rate to zero.

The underlying reason is the ADR 0017 principle. Openness reads ALSA, which
is **what drafters believe a card is worth**; `base` reads GIH WR, which is
**what it is actually worth**. Where the two disagree the win rate is the
one telling the truth, so the belief adds nothing on top of it.

ALSA itself is not retired. It is still ingested, stored on `cards`, shown
in the review's card panel and passed to the prompt brief. It is simply no
longer a scoring input.

### 2. Role keeps one branch

`creature_weight = 0.0` at 20.7% leverage is a measurement, not an
unexercised constant. The creature branch and `target_creatures` are
deleted; `role` is now removal scarcity and nothing else.

The double-counting is measurable, and it is the same table ADR 0017 used:

| | n | mean GIH WR | vs the rest |
|---|---|---|---|
| creatures | 112 | 56.07 | **+2.88pp** |
| `_removal_` tagged | 14 | 57.34 | **+2.33pp** |
| by mana value | — | 54.6–56.7, non-monotone | **no signal** |

A creature's win rate already contains +2.88pp of "this is a creature".

**Why removal survives the identical argument.** Its premium is nearly as
large, so the double-counting is real there too — yet the fit wanted a
positive weight, just a smaller one. The difference is scarcity. Against a
target of 14 creatures with a deficit that saturates three short, almost
every pool in almost every draft is "short of creatures", so the branch
fired nearly unconditionally and amounted to a flat bonus on a tag. Against
a target of 4 removal spells saturating two short, running out is a genuine,
varying property of *your* pool — the kind of thing GIH WR cannot contain.
At the fitted 0.5 the term also stops outranking a two-point quality gap,
restoring the cap ADR 0003 §1.4 set and ADR 0005 predicted would have to
lift.

### 3. The fitted constants are adopted

`ramp_start` 0, `ramp_span` 14, `curve_weight` 0.25, `removal_weight` 0.5.

The ramp now rises from the first pick instead of sitting flat for four, and
still pins at pick 14, the last pick of a HOB pack. P1P1 is therefore no
longer exactly card quality: it carries 1/14 of the shape terms, which on a
fully collapsed pool is 0.43pp of colour tax and 0.018pp of curve. Against a
`solid_gap` of 2.0 that is a tiebreaker toward your own colours, which is
the right behaviour at pick 1 and was previously unavailable at any strength.

**`ramp_start` is kept as a tunable even though HOB fitted it to zero.** ADR
0013 makes these format-level; a slower format may well want a pick or two
of free speculation before the pool binds, and only one format has been
measured. Deleting the parameter would bake a single format's measurement
into the shape of the ramp.

### 4. Marginal role was considered and rejected — but not for the reason first recorded

The obvious alternative to deleting the creature branch was to reformulate
it as a margin, exactly as ADR 0017 did for synergy: pay the card only when
the pool is *unusually* short of creatures, rather than short of a fixed
target.

An earlier note argued this was not even expressible, on the grounds that
creature counts are a property of the pool and so identical for every card
in the pack, making a per-pick re-centring a no-op on the loss. **That
argument is wrong and is recorded here so it is not relied on again.** The
branch contributes `creature_weight × λ × min(1, deficit/3)` to every
creature in the pack and nothing to every non-creature; re-centring the
deficit changes that constant, which changes the creature-versus-
non-creature spread, and so can change the argmax. What it cannot do is
reorder two creatures against each other — but the absolute form could not
do that either.

So marginal role is expressible, and by this ADR's own principle it has a
case: "my pool is unusually creature-light" is a fact about the pool that no
card's win rate can contain, precisely like a curve hole.

It is nevertheless **not built here**, for three reasons. Testing it needs a
31-minute re-extract and a 12-minute re-fit, since the feature cache would
need `E[creature_count | pack, pick]`. The fit's current answer is zero, so
shipping the deletion is the honest state of the evidence. And the deleted
code is recoverable from git, so a later experiment loses nothing. If it is
built, the quantity to centre on is the one
`scripts/derive_target_curve.py` already reports.

## Consequences

**The decomposition lost a field,** so everything that enumerates the terms
changed with it: `CardFitness.openness`, `_breakdown` in
`ingest/draft_link.py`, `FitnessBreakdown` in `review/src/lib/review/types.ts`
and `BREAKDOWN_TERMS` in `PackView.svelte`. The admin popup now shows four
conditioning terms rather than five. `score_pack` also loses its `pick`
argument and the backtest's `_card_total` its `format_avg_wr`: openness was
the only reader of either. `FitnessConfig` is down from 18 tunables to 13,
and the backtest's fittable grid from 13 constants to 8.

**Observed** on the three reference drafts, with the two halves separated so
the deletions can be judged apart from the new constants:

| draft | before | deletions only | deletions + fitted constants |
|---|---|---|---|
| `f1daa925` WR | 30/7/1/4 | **30/7/1/4** | 32/5/1/4 |
| `d9ac6765` BR | 34/3/0/5 | 34/2/0/6 | 34/2/0/6 |
| `dba56c2c` UG | 23/9/4/6 | **23/9/4/6** | 24/8/4/6 |

The deletions on their own leave two of the three splits untouched and move
a single pick on the third — which is what "these terms were paying for
something already priced" looks like from the outside. The new constants
account for the rest, all of it `questionable` becoming `solid` or
`indifferent`.

**The mistake counts do not move at all**: 1, 0 and 4 in every
configuration. Since ADR 0008 makes `mistake` the only verdict that earns a
written explanation, no relevant pick and no critique text changes. The
function became slightly more forgiving at the margin and no less decisive
where it matters.

Role firings fall from 98/169/106 scored cards to 12/20/23, and the term's
largest value from 1.25pp to 0.50pp — the creature branch had been the bulk
of what role ever did.

**Costs.** Two terms' worth of design is gone, and with them the only part
of the function that read the draft table rather than the card pool: nothing
now notices that a colour is flowing. If that signal is real, it will have
to be rebuilt on something better than ALSA. The holdout gain for the whole
fit is 0.062pp of pick-agreement loss (1.4454 → 1.3833), and target 2's
correlation is flat (−0.1299 → −0.1294) — so this is a simplification that
pays for itself slightly, not a leap.

**The feature cache was invalidated** — its fingerprint covers
`fitness.py` — and has been rebuilt. It is 562 MB rather than 711 MB, the
three dropped per-card features being `alsa`, `has_creature` and
`oncolor_creature`.

### Confirmed by the re-fit (2026-10-12, same day)

The re-extract and re-fit on the new 8-constant grid have now run, and
**no constant moved**. The four values adopted above are therefore
measured on a clean cache, not inherited from a fit in which two
about-to-be-deleted terms were still competing with them:

| constant | value | leverage |
|---|---|---|
| `ramp_start` | 0 | 23.0% |
| `ramp_span` | 14 | 23.2% |
| `tax_value` | 6.0 | 43.5% |
| `curve_weight` | 0.25 | 30.4% |
| `removal_weight` | 0.5 | 13.1% |
| `target_removal` | 4 | 10.0% |
| `synergy_weight` | 0.75 | 46.1% |
| `synergy_cap` | 5.0 | 25.3% |

Holdout loss 1.3833pp, top-1 agreement 52.3%, target 2 Pearson r =
−0.1294: identical to the pre-deletion fitted config, so the deletions
cost nothing measurable on either target. Every surviving constant now
carries at least 10% leverage, and the report has **no unmeasured-constant
warnings left** — the three that previously read 0.0% (`openness_dead_alsa`,
`replacement_offset`, `target_creatures`) were precisely the ones the
deleted terms gated.

Notably `ramp_span` held at 14 from a 2–28 grid. The ramp wants to pin at
the last pick of pack 1 on its own merits, not because openness was
confined there by ADR 0016.

**Revisit when:** marginal role is built, per §4; or if a table-reading
signal is wanted again, in which case start from the gap between ALSA and
ATA rather than from ALSA alone. The constants themselves are settled for
HOB; the next format will need its own fit (ADR 0013).
