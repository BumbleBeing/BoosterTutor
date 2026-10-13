# ADR 0006 — The synergy term: pricing tag-pair fit against the pool

**Status:** Proposed · **Date:** 2026-09-18 · **Relates to:** ADR 0003 §1
(the fitness function), ADR 0004 (tag taxonomy, self-payoff), ADR 0005
(fitness classes) · **Supersedes:** ADR 0004's counting statement in its
Consequences ("ordinary tags do not have this problem, because their enabler
count is a count of distinct cards")

---

## Context

ADR 0003 gives the fitness function four terms — `base`, `curve`, `role`,
`openness` — and argues in §1.2 that archetype-scoped GIH WR is already "our
synergy layer," reserving hand-written synergy rules for "set mechanics the
data genuinely can't express, and each one needs its own justification." ADR
0004 built the vocabulary for those hand-written rules — `tags`,
`tag_pairs`, `card_tags` — but never specified how anything reads them:
"DraftDouble has no fitness function at the time of writing."

[Issue #19](https://github.com/BumbleBeing/BoosterTutor/issues/19) asks for that
reader: a fifth fitness term that turns `tag_pairs` and the current pool
into a per-card boost, alongside `base`/`curve`/`role`/`openness`.

## Decision

### 1. What this term is for

Archetype-scoped GIH WR averages over every deck in a colour pair; it can't
see that *this* pool has already committed to a specific, narrower game-plan
(three sacrifice outlets, say) that most decks in that colour pair never
build toward. **The synergy term exists to give less conventional decks
built around a specific, tagged game-plan the credit that a colour-pair
average smears away** — not to patch thin archetype samples, which
`min_games`/`replacement_wr` and the σ-aware bands (ADR 0003 §2.1) already
handle. A term that grew or shrank with how many games a card had would be
solving the wrong problem.

### 2. The graph walk: direct edges only, never imputed

The term walks only the `tag_pairs` rows that were actually authored:

- **No transitivity.** A chain `disposable_creature → creature_sac_outlet →
  dies_trigger` does not let a `disposable_creature` in the pool boost a
  `dies_trigger` card in the pack. Only `creature_sac_outlet`'s count does
  that, because only that edge was authored. `CONTEXT.md`'s Tags section is
  explicit that tags are "assigned directly and exhaustively, with no
  hierarchy" — the tags on a card are the whole truth about it, and
  inferring a multi-hop relationship nobody wrote down would violate that.
  It also keeps the mechanism a flat, auditable sum instead of a graph-walk
  with compounding coefficients, and it gives the correct incentive: an
  unconverted enabler two hops away isn't yet doing anything for the payoff,
  so the fitness term shouldn't say it is.
- **No imputed symmetry.** A single authored edge is read from *either* end:
  scoring an enabler candidate counts payoffs already in the pool; scoring a
  payoff candidate counts enablers already in the pool. That is the same
  edge, read both ways — not a second edge. A true reverse relationship (two
  tags that each reward the other, at possibly different coefficients) needs
  its own second row, authored by hand. The mechanism never assumes one
  exists just because the tags involved could support it.

### 3. Counting: copies, not distinct cards

Every tag pair counts **copies of the complementary tag already in the
pool**, including duplicate picks of the same card. This overturns ADR
0004's claim that ordinary tags "do not have this problem" and should count
distinct cards — two copies of the same narrow enabler now count as two, the
same as two different enablers would. One counting rule applies everywhere,
which is also what makes self-payoff fall out of the general rule for free
(§7) instead of needing its own code path.

### 4. Saturation: a smooth per-pair curve, not a hard knee

Not every pair behaves the same past the first copy. Creature-typal synergy
is "the more, the merrier" — no saturation. A narrower enabler/payoff pair
commonly saturates fast — most of the value is in the first one or two
copies. Both are modelled with one formula and one optional per-edge
parameter, `cap`:

```
n     = copies of the complementary tag already in the pool
n_eff = n                     if the edge has no authored cap   (pure linear)
      = cap * n / (n + cap)   if the edge has an authored cap   (saturates smoothly toward `cap`)
```

`n_eff` approaches `cap` as `n` grows, but never hits it exactly — there is
no count at which one more copy is worth literally nothing, only ever less.
A lower `cap` means a steeper early rise and a harsher drop-off; a higher
`cap` approximates the uncapped, linear case over the range of counts a
draft pool ever reaches. Worked values at `cap = 2`: `n=1 → 0.67`, `n=2 →
1.0`, `n=3 → 1.2`, `n=4 → 1.33`, converging on 2. No cap is the default —
most pairs need no migration or authored value at all.

This needs one new nullable numeric column on `tag_pairs` (`cap`, default
`NULL`); adding it is ticket #20's concern, not this one's, but the shape
above is what it must support.

### 5. Weight and ceiling

```
raw     = sum over every (tag on the candidate card, edge touching that tag)
          of coefficient(edge) * n_eff(edge)
synergy = min(synergy_cap, synergy_weight * raw)
```

Two new tunables, both to be found in the ADR 0003 §3 backtest, not trusted
as written here:

- `synergy_weight` — pp per coefficient unit, playing the role
  `curve_weight`/`role_weight` play for their terms.
- `synergy_cap` — a **loose** ceiling on the total (placeholder: 5pp), so
  that a fluke in the graph — several pairs firing on one card at once —
  cannot let a tag match outweigh a large `base` or `role` gap outright.
  This is a deliberate backstop, not a noise-based cap like `openness_cap`
  (1.5pp, capped hard because that term is likely noise): a correctly-tagged
  niche synergy is a real effect and is expected to matter more than 1.5pp
  in the right pool, just not without limit.

Unlike `curve` and `role`, **synergy is not scaled by the commitment ramp
λ.** λ governs uncertainty about which archetype the pool is committing to;
two specific tagged cards already sharing the pool have already resolved
that uncertainty for each other, independent of what the rest of the draft
does. A P1P2 payoff with a P1P1 enabler already in the pool is worth its
full synergy value, not a λ-damped fraction of it.

### 6. Decomposition, for the brief

The term returns more than a scalar. Every firing edge produces a row:

```python
@dataclass
class SynergyFiring:
    tag_on_card: str
    complementary_tag: str
    pool_count: int        # n
    effective_count: float # n_eff
    coefficient: float
    pp: float

@dataclass
class SynergyResult:
    total: float                    # feeds CardFitness.synergy, capped per §5
    top_firings: list[SynergyFiring]  # at most 2, see below
```

Only the **top 2 firings by pp**, each at or above a 0.1pp floor, are kept
for `top_firings`; anything smaller is computed (it still contributes to
`total`) but never surfaced. This mirrors how ADR 0003 §1.6 already hands
the prompt `colour_fit` as *the* reason rather than all ten archetype
weights: the brief gets the one or two tags that actually explain the
number, not a itemised ledger of every tag on the card.

### 7. Self-payoff and `both`-kind tags need no special case

Both fall out of §§2–4 without any branch in the algorithm:

- **Self-payoff.** A self-payoff tag `S` pairs with itself, so `other == S`
  and `n` is just "copies of `S` already in the pool" — exactly ADR 0004's
  diagonal rule, produced by the general formula with no extra code.
- **`both`-kind tags.** A `both` tag (e.g. `creature_sac_outlet`) is simply a
  tag that happens to be the enabler side of one edge and the payoff side of
  another. The algorithm never inspects `kind` at all — only `tag_pairs`
  rows. `kind` remains purely an authoring-time constraint, already enforced
  in the store per ADR 0004.

## Consequences

**Good.** Niche, tag-driven game-plans get credit that a colour-pair average
cannot see, which was the whole justification (§1). The counting rule is
uniform (§3), so self-payoff and `both`-kind tags need zero special-case
code (§7). The saturation and weight shapes (§4–5) reuse ADR 0003's existing
style (`min`/ramp-style deficits become a smooth asymptote instead) rather
than inventing new mathematical machinery.

**Costs.** Three new tunables (`synergy_weight`, `synergy_cap`, and the
per-edge `cap`) on top of ADR 0003's eight and ADR 0005's three. The
per-edge `cap` needs a schema column (ticket #20). This ADR also reverses
part of ADR 0004: taxonomy authored so far assumed distinct-card counting
for ordinary pairs, and that assumption no longer holds — worth a pass over
the live HOB taxonomy once implemented, to check whether any authored
coefficient was sized with distinct-card counting in mind.

**CONTEXT.md.** The **Threshold Synergy** entry is retired: it described a
hard gate ("gains nothing beyond a fixed count") that turned out not to
match what was actually wanted, once a concrete formula was on the table.
The smooth per-edge `cap` in §4 covers the drafting behaviour that entry was
reaching for.

**Revisit when:** the backtest can't find a `synergy_weight`/`synergy_cap`
pair that beats the no-synergy baseline on picks where a tagged game-plan is
in play; or a real set needs a hard gate after all (a payoff that is
genuinely inert below some count), which this design does not support and
would need to be designed separately if it comes up.

## Alternatives rejected

**Transitive propagation through a chain of edges.** Would let far-off,
unconverted enablers boost a payoff several hops away. Rejected: violates
the taxonomy's exhaustive, no-hierarchy principle, and compounding
coefficients across hops are hard to reason about or tune (§2).

**Imputed symmetric edges.** Treating an authored `(A, B)` coefficient as
automatically pricing a `(B, A)` relationship too. Rejected: the taxonomy is
deliberately hand-authored human judgement (ADR 0004); inferring a direction
nobody wrote down makes the mechanism smarter than the person who authored
it (§2).

**Hard-knee cap (`n_eff = min(n, cap)`).** The first proposal for §4, matching
ADR 0003's `curve`/`role` shape exactly. Rejected in favour of a smooth
saturating curve: real drafting judgement expects each further copy to
help less, not to help *and then suddenly not at all* past a fixed count.

**Distinct-card counting for ordinary pairs.** ADR 0004's original rule.
Rejected in favour of uniform copy-counting (§3): a second copy of a narrow
enabler is worth something, even if less than a second *different* enabler
would be, and one rule everywhere is simpler than two.
