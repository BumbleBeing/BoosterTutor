# ADR 0003 — Pick grading: the fitness function and how we validate it

**Status:** Proposed · **Date:** 2026-08-24 · **Supersedes:** the placeholder thresholds in `development_plan.md` §3.3

---

## Context

Draft Review has to answer, for each of 45 picks: *was this the right card, and if not, how wrong was it and why?* The verdict must be computed in Python — Claude explains it, never decides it (see `CLAUDE.md`, core architectural rule).

A first instinct is: score every card in the pack, take the top 2–3, and if the player's pick isn't among them, call it suboptimal. That framing has two defects serious enough to sink the product:

1. **Rank is the wrong signal.** Most picks are close. Flagging every non-top-1 pick means most of the 45 blurbs read "suboptimal," including plenty that were fine. Users stop trusting the tool, and the three genuinely useful flags get ignored with the rest.
2. **Fixed weights are wrong at both ends of the draft.** A color-commitment penalty that is correct at P3P13 is nonsense at P1P1, when you have no colors to be committed to.

This ADR fixes both, and specifies how we find out whether the result is any good.

## Decision

Score every card in the pack in **percentage points of win rate (pp)**, on a single interpretable scale. Grade the pick on the **size of the gap** between the best available card and the one taken, measured against the statistical noise in the underlying data — not on rank. Return the score **decomposed** into named terms so the prompt can say *why*.

---

## 1. The fitness function

```
fitness(card, pool, t) = base(card, pool, t)      # conditioned card quality
                       + curve(card, pool, t)      # marginal curve value
                       + role(card, pool, t)       # removal / creature scarcity
                       + openness(card, pack, t)   # signal that this colour is flowing
```

All four terms are in pp. `t` is the global pick index, 1–45.

### 1.1 The commitment ramp

One function governs how much the pool constrains the pick. Everything downstream reads it.

```python
def commitment(t: int, cfg) -> float:
    """0.0 = pool tells us nothing yet; 1.0 = pool fully determines what's playable."""
    return min(1.0, max(0.0, (t - cfg.ramp_start) / cfg.ramp_span))
```

Starting values: `ramp_start = 4`, `ramp_span = 18`. So λ is 0 through P1P4, rises linearly, and is pinned at 1.0 from P2P7 onward. These are two of the few numbers we tune.

### 1.2 Base — conditioned card quality

> **Superseded in part.** ADR 0007 replaced the belief distribution with a single predicted archetype. ADR 0011 then normalized the archetype-scoped rate against that archetype's own win rate, because a scoped rate carries the pair's strength as well as the card's fit with it.

This is the important idea, and it replaces the hand-tuned "off-colour penalty" entirely.

Rather than scoring a card in the abstract and subtracting a penalty for being off-colour, we hold a **belief distribution over the ten two-colour archetypes** and score the card as an expectation across it. Early in the draft the belief is flat, so the score is close to raw card quality. Late in the draft it collapses onto one or two archetypes, and a card that isn't playable in them scores at replacement level automatically — no penalty coefficient required.

**Step 1 — commitment to each archetype.** For each colour pair `A`, sum how much value the pool already holds in it:

```python
def archetype_commitment(pool, A, stats) -> float:
    total = 0.0
    for card in pool:
        if playable_in(card, A):                 # colour identity ⊆ A, or colourless
            wr = stats.gih_wr(card, archetype=A) # falls back to overall WR if scarce
            total += max(0.0, wr - stats.format_avg_wr)
    return total
```

Good cards contribute more than filler, and depth contributes too. That is the behaviour we want: six solid black cards should commit us harder than two black bombs and four blanks.

**Step 2 — turn commitments into a belief distribution,** blended by λ against a prior:

```python
def archetype_beliefs(card, pool, t, stats, cfg) -> dict[str, float]:
    lam = commitment(t, cfg)
    scores = {A: archetype_commitment(pool, A, stats) for A in TEN_PAIRS}
    posterior = softmax(scores, temperature=cfg.tau)      # tau ≈ 1.5

    # Prior = "if I take this card, I'm heading somewhere it's playable."
    ok = [A for A in TEN_PAIRS if playable_in(card, A)]
    prior = {A: (1 / len(ok) if A in ok else 0.0) for A in TEN_PAIRS}

    return {A: (1 - lam) * prior[A] + lam * posterior[A] for A in TEN_PAIRS}
```

**The prior is conditioned on the card, and that is deliberate.** The naive choice — a flat prior over all ten pairs — is subtly broken: a mono-blue card is playable in only four pairs, so even at P1P1 with an empty pool it would score below its true win rate, and a gold card (playable in one pair) would be hammered. The function would encode a bias against gold cards that has nothing to do with drafting and everything to do with the arithmetic.

Conditioning on the card fixes it, and is the more correct model anyway. The question at P1P1 is *"if I take this, where am I heading?"* — and the answer is: somewhere this card is playable. With this prior, λ = 0 gives back exactly the card's unconditioned win rate, for every card, which is the behaviour we want at the start of a draft. As λ rises, the pool's posterior takes over and the card's own prior stops mattering.

**Step 3 — score the card as an expectation:**

```python
def base(card, pool, t, stats, cfg) -> float:
    beliefs = archetype_beliefs(card, pool, t, stats, cfg)
    return sum(
        p * (stats.gih_wr(card, archetype=A) if playable_in(card, A)
             else cfg.replacement_wr)             # ≈ format_avg_wr - 3.0
        for A, p in beliefs.items()
    )
```

`replacement_wr` is what an unplayable card is worth: roughly the win rate of the filler you'd run instead. Start it 3pp below format average.

Note what falls out of this for free: **archetype-scoped GIH WR is our synergy layer.** A card at 53% overall and 57% in Boros is telling us about synergy, measured over millions of games, with no hand-authored card-pair table to maintain across four sets a year. Hand-written synergy rules are reserved for set mechanics the data genuinely can't express, and each one needs its own justification.

### 1.3 Curve

> **Amended by ADR 0010 (2026-09-19):** lands are excluded from this term on both sides — a land neither fills a curve slot nor has a curve of its own — which also matches how `target_curve` was derived. The example targets below are folklore; the measured ones are in DraftDouble's `docs/target-curve.md`.

Only matters once there's a deck shape to disturb, so it scales with λ:

```python
def curve(card, pool, t, cfg) -> float:
    lam = commitment(t, cfg)
    mv = min(card.cmc, 6)
    have = count_playables_at_mv(pool, mv)
    want = cfg.target_curve[mv]        # e.g. {1:1, 2:5, 3:4, 4:3, 5:2, 6:1}
    if have < want:
        return cfg.curve_weight * lam                      # fills a hole
    excess = have - want
    return -cfg.curve_weight * lam * min(1.0, excess / 2)   # piling on
```

`curve_weight ≈ 0.75pp`. Deliberately small: curve matters, but it does not outrank a two-point card-quality difference, and a function that says otherwise will give bad advice. Derive `target_curve` from the public dataset — what the curves of winning decks in *this* format actually look like — rather than from folklore.

### 1.4 Role

> **Amended by ADR 0010 (2026-09-19):** `role_weight` splits into `removal_weight` 1.25pp and `creature_weight` 0.40pp, so removal is worth about three times a body; the removal branch therefore exceeds the 1pp ceiling this section implies, as ADR 0005 predicted it would need to. Both targets are now measured from winning decks rather than guessed, and removal is the hand-authored `_removal_` tag alone (ADR 0007 §2).

Same shape, applied to removal and creature counts against format-specific targets:

```python
def role(card, pool, t, cfg) -> float:
    lam = commitment(t, cfg)
    score = 0.0
    if card.has_tag("removal"):
        deficit = max(0, cfg.target_removal - count_tag(pool, "removal"))
        score += cfg.role_weight * lam * min(1.0, deficit / 2)
    if card.has_tag("creature"):
        deficit = max(0, cfg.target_creatures - count_tag(pool, "creature"))
        score += cfg.role_weight * lam * min(1.0, deficit / 3)
    return score
```

`role_weight ≈ 0.75pp`. Tags come from the `card_tags` table computed at ingest time (ADR 0002), not from regexes at request time.

### 1.5 Openness

The signal term: is this colour actually flowing? Strongest early, so it scales with `(1 − λ)`.

```python
def openness(card, pick, t, stats, cfg) -> float:
    lam = commitment(t, cfg)
    alsa = stats.alsa(card)                   # the pick at which this card is usually gone
    lateness = pick - alsa                    # picks the card is still here PAST its ALSA
    raw = cfg.openness_weight * lateness      # openness_weight ≈ 0.25pp per pick of lateness
    return (1 - lam) * clamp(raw, 0.0, cfg.openness_cap)   # cap ≈ 1.5pp; never negative
```

Capped hard, because it is the term most likely to be noise. A card sitting five picks past its ALSA is real evidence; a card one pick past it is nothing.

**Amended 2026-09-18** ([#29](https://github.com/BumbleBeing/BoosterTutor/issues/29)), two corrections found while implementing this term in DraftDouble:

1. **The sign.** The original wrote `lateness = expected_pick − current_position`, which is backwards relative to the sentence above it and to what ALSA (Average Last Seen At) means. A card that usually disappears by pick 2 and is in front of you at pick 7 is *five picks late*, and that is `7 − 2`, not `2 − 7`. Lateness is now `pick − ALSA`.
2. **The clamp is one-sided.** The original clamped to `[−cap, +cap]`, so a card seen *earlier* than its ALSA got a penalty. That has an unintended consequence at the start of a pack: at pick 1 every card is "early" (`1 − ALSA` is negative for all of them), and least early for the cards that are usually taken first. Low ALSA correlates with high win rate, so the term became a capped bonus for good-in-general cards — a second helping of card quality, not information about the table. On a real HOB draft P1P1's best card changed on this term alone. Openness now clamps to `[0, cap]`: it can only add, and only when a card is genuinely late. A card seen earlier than usual is normal, not a signal.

Neither change touches the tunables; `openness_weight` and `openness_cap` remain as listed in §3.5.

### 1.6 The decomposition is the output

Never return a bare number. Return the parts:

```python
@dataclass
class CardFitness:
    oracle_id: UUID
    total: float
    base_unconditioned: float   # the card's overall GIH WR — the number 17Lands shows
    colour_fit: float           # base - base_unconditioned  (the counterfactual)
    curve: float
    role: float
    openness: float
    n_games: int                # sample size behind the win rates
```

`colour_fit` comes out as a subtraction rather than a coefficient — it's the difference between what the card is worth in the abstract and what it's worth to *this* pool. That's exactly the sentence a coach wants to write, and it means the prompt can say "this wasn't a card-quality mistake, it was a colour-commitment mistake."

Worked example, computed with the formulas above (`τ = 1.5`, format average 56.0, replacement 53.0) — P2P3, pool eight cards deep in black-red, a strong blue card in the pack:

```
base_unconditioned 56.80  |  colour_fit −2.81  |  curve +0.00  |  role +0.00  |  openness +0.30  →  54.29
```

λ is 0.78 at this point, the pool's posterior sits at about 0.85 on black-red, and the blue card retains roughly a quarter of the belief mass — partly from its own prior, partly because UB is still a live pivot given five black cards. The same card at P3P5 with a twenty-card pool scores `colour_fit −3.80`, the full replacement discount, because λ has pinned at 1.0 and the posterior has collapsed onto one pair. That progression — a shrinking allowance for pivoting as the draft goes on — is the behaviour the whole design exists to produce.

**Diagnostic for τ:** it controls how decisively the pool picks a lane, and it interacts with the scale of the commitment sums, so it cannot be tuned in isolation. Sanity check: by mid-pack-2 the leading archetype should hold most of the belief mass, and by pack 3 nearly all of it. If a twenty-card pool still spreads belief across four pairs, τ is too high.

---

## 2. From fitness to a verdict

### 2.1 The noise floor

Win rates are estimates. A gap smaller than the error bars is not a mistake, and claiming otherwise is how a coach loses credibility.

```python
def stderr_pp(wr_pct: float, n_games: int) -> float:
    p = wr_pct / 100
    return 100 * math.sqrt(p * (1 - p) / max(n_games, 1))

gap   = best.total - picked.total
sigma = math.hypot(stderr_pp(best.base_unconditioned, best.n_games),
                   stderr_pp(picked.base_unconditioned, picked.n_games))
```

At a 55% win rate over 5,000 games, that's about 0.7pp per card and ~1.0pp for the pair. Gaps below that are noise. Say nothing.

### 2.2 Bands

Every threshold is the larger of an absolute gap and a multiple of σ, so thin data automatically widens the bands:

| Verdict | Condition |
|---|---|
| `insufficient_data` | either card below `min_games` (start: 1,000) |
| `optimal` | `gap < max(0.5, 1.0σ)` |
| `reasonable` | `gap < max(2.0, 1.5σ)` |
| `questionable` | `gap < max(4.0, 2.0σ)` |
| `mistake` | otherwise |

What that means in practice, for two cards both around 55%:

| Games each | σ | `optimal` below | `reasonable` below | `questionable` below |
|---|---|---|---|---|
| 1,000 | 2.22pp | 2.22 | 3.34 | 4.45 |
| 2,000 | 1.57pp | 1.57 | 2.36 | 4.00 |
| 5,000 | 0.99pp | 0.99 | 2.00 | 4.00 |
| 20,000 | 0.50pp | 0.50 | 2.00 | 4.00 |

Read the top row carefully: in a set's first week, when nothing has 2,000 games behind it, almost every pick lands in `optimal` or `reasonable` and the app has very little to say. **That is correct behaviour, not a bug** — we genuinely do not know yet. Surface it in the UI ("early data for this set; grades will sharpen") rather than manufacturing confidence.

### 2.3 The speculation override

A function like this will call an off-colour bomb at P1P4 a mistake. Frequently it isn't — taking the best card early and letting the draft come to you is correct play.

```python
if (t <= cfg.spec_window                                    # early, ~pick 8
        and picked.base_unconditioned >= nth_best_unconditioned(pack, 2)
        and picked.colour_fit < 0):
    verdict = downgrade_one_band(verdict)
    flags.append("speculative_first_pick")
```

The flag reaches the prompt, so the blurb can acknowledge the reasoning — "a reasonable speculative pick; the cost is that you were already six cards into Boros" — rather than scolding. Hate-drafting and information the log doesn't contain are handled the same way: prefer "reasonable" over "wrong" whenever a competent player could have had a reason.

### 2.4 Aggregate, because that's where the coaching is

Pick-level grades are the raw material. The feedback people remember is pattern-level, and the decomposition hands it to you cheaply: which term dominated the losses across the draft (colour fit? curve? raw quality?), how many mistakes were speculation-adjacent, at which pick the player's committed archetype stopped matching their picks. Compute these over the 45 picks now, and over a user's history once accounts land (Phase 7).

### 2.5 Versioning

```python
GRADING_VERSION = "0.1.0"
```

Bump on any change to weights or bands, store it on every saved review alongside `prompt_version` and `data_snapshot_date`. Without it you cannot answer "why does this draft grade differently than it did last month?"

---

## 3. Backtest procedure

Everything above contains roughly eight tunable numbers. Hand-tuning them by feel produces a function that encodes your own drafting biases and then confidently teaches them to other people. So we validate against how strong drafters actually pick.

### 3.1 Data

17Lands' public **draft** dataset — pick-level, one row per pick:

```
https://17lands-public.s3.amazonaws.com/analysis_data/draft_data/draft_data_public.{SET}.{FORMAT}.csv.gz
```

Confirm the exact path and the column names against the current file header before writing code against them — do not trust this document or any blog post. Expect columns identifying the draft, the pick and pack number, the card taken, per-card `pack_card_*` columns marking pack contents, per-card `pool_*` columns marking what's already drafted, plus rank, win-rate bucket, and event record fields.

The file is wide (a column per card per zone) and long (millions of rows). Read it once in chunks, reshape to a compact long format — `(draft_id, pack, pick, pack_card_ids[], pool_card_ids[], picked_id)` — and cache as Parquet. Every subsequent tuning run reads the Parquet in seconds instead of re-parsing gigabytes.

### 3.2 Cohorts

Split drafters by skill, using the user win-rate bucket and/or event match wins:

- **Strong** — top win-rate bucket, or 7-win Premier Draft runs
- **Weak** — bottom bucket

Both cohorts matter, and the second one is the clever part: see 3.4.

### 3.3 Splits

- **Tune** on one set.
- **Validate** on a *different* set, untouched during tuning.

Cross-set validation is not optional. A function tuned on a single format will learn that format's quirks — an aggressive set will teach it to overweight two-drops — and look brilliant right up until someone drafts a slow set with it.

### 3.4 Metrics

| Metric | What it tells you |
|---|---|
| **Top-1 agreement** with strong drafters | Headline accuracy |
| **Top-3 agreement** with strong drafters | Whether the right card at least surfaces |
| **Mean gap on disagreement** | Whether disagreements are small (fine) or large (alarming) |
| **Discrimination gap** = agreement(strong) − agreement(weak) | **The metric that matters most** |
| **Baseline delta** vs "always take the highest raw GIH WR" | Whether the complexity earns its keep |

The discrimination gap is the real test. A function that agrees equally with good and bad drafters is measuring *conventionality*, not quality, and cannot coach. You want it to agree with strong drafters clearly more often than with weak ones.

The baseline comparison is the honesty check. If naively taking the highest raw win-rate card matches strong drafters about as often as your function does, then the colour/curve/role machinery is decoration. Expect the naive baseline to be respectable early in a pack and to fall apart in pack 3, which is exactly where λ ≈ 1 should let you win.

Always report metrics **segmented by pick number** (P1p1–5, P1p6–15, pack 2, pack 3). Late-pack picks are close to forced, so agreement there should be high; if it isn't, your ramp or your replacement value is wrong. Early-pack agreement will be lower, and that's expected — genuine disagreement between good drafters is highest at P1P1.

### 3.5 The tuning loop

```python
PARAMS = ["ramp_start", "ramp_span", "tau", "replacement_wr",
          "curve_weight", "role_weight", "openness_weight", "openness_cap"]

def objective(cfg, picks_strong, picks_weak) -> float:
    return top1_agreement(cfg, picks_strong) - top1_agreement(cfg, picks_weak)
```

Coordinate descent is enough: sweep one parameter across a small grid holding the rest fixed, keep the best, repeat two or three passes. Eight parameters over ~50k sampled picks is a laptop-scale job, and the tiny parameter count is your main protection against overfitting. Resist adding a ninth parameter without evidence that the eight cannot do the job.

Log every run — parameters, metrics, dataset, date — to `docs/decisions/grading-runs.md`. Tuning is an experiment, and untracked experiments get repeated.

### 3.6 The outcome check (stretch)

The metrics above measure agreement with strong players, which is a proxy. The real question is whether picks the function dislikes actually lose more. Bucket picks by fitness gap and compare match win rates across buckets.

Be honest about the noise: one pick rarely decides a draft, and the effect will be small and slow to reach significance. Treat a clear monotonic trend as encouraging confirmation, and treat its absence as inconclusive rather than as refutation.

### 3.7 Acceptance criteria

Set the real bar after the first run — I don't have reliable public figures for what top-1 agreement is achievable on this task, and inventing a precise target now would be false precision. Starting posture:

- Top-3 agreement with strong drafters should be **clearly higher** than top-1, and high in absolute terms; if the right card frequently isn't even in the top 3, something is broken rather than untuned.
- The **discrimination gap must be positive and stable across both sets.** If it is near zero, do not ship — grade only obvious mistakes (large gaps) and say nothing about close picks until it improves.
- The function must **beat the raw-GIH baseline on picks 8+**. If it doesn't, delete the terms that aren't earning their place.
- Whatever numbers the first run produces, record them here as the baseline that future changes must beat.

---

## Consequences

**Good.** Verdicts are noise-aware, so the tool stays quiet when it should. Weights are validated against real drafter behaviour rather than intuition. The decomposition gives the prompt a *reason*, which is what makes a blurb coaching instead of a scoreboard. Synergy comes from measured archetype data, so it doesn't need maintenance every set.

**Costs.** Ten archetype hypotheses per card per pick is more computation than a single lookup — still trivial (45 picks × ~14 cards × 10 pairs is a few thousand dictionary operations), but not free. The backtest is real work, probably two sessions, before Draft Review can ship with confidence. And archetype-scoped stats have thinner samples than overall stats, so the `min_games` fallback path will be exercised often in a set's first two weeks.

**Revisit when:** the discrimination gap stops improving with tuning; a set's mechanics defeat the archetype-scoped approach; or there's enough labelled data to justify fitting the weights properly rather than searching a grid.
