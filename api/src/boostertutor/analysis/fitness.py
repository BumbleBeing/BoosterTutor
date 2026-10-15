"""The pick-fitness function.

Ported unchanged from DraftDouble's `analysis/fitness.py` on 2026-10-14,
where it was built (DraftDouble ticket #20) and backtested against 43,650
HOB drafts. References below to tickets, BIG_FIX_#1 and `docs/` files are
DraftDouble's.

Design: ADR 0003 s1 (base, curve, role, the commitment ramp and the
CardFitness decomposition), ADR 0005 (option value, fitness classes, verdicts)
and ADR 0006 (tag synergy). Every term is in percentage points of win rate.

ADR 0018 is the most recent structural change: it retired the openness term
outright and cut the creature branch out of role, on the backtest's finding
that both were paying for things a card's GIH WR already prices. What
remains is base + color fit + curve + role + synergy.

This module is pure. Card data and statistics come in as plain values; nothing
here reads the database.

A `card` is a dict with at least `oracle_id` and `colors` (sorted WUBRG
letters, "" for colorless); later terms also read `cmc`, `tags` and the
optional `color_options` (see `color_options()`, for hybrid cards). A `pool`
is a list of such cards, one entry per pick, so duplicates are real copies.
"""

import itertools
import re
import uuid
from dataclasses import dataclass, field

# A card's oracle id. DraftDouble used text ids; BoosterTutor uses UUIDs. The
# function only ever compares and hashes ids, so the ported tests' short
# strings ("a", "c1") work as well.
OracleId = uuid.UUID


@dataclass(frozen=True)
class FitnessConfig:
    """Every tunable in one place.

    Starting values are the ADRs' suggestions. None of them has been validated
    yet: ADR 0003 s3's backtest is what finds the real values, and that is a
    separate ticket.
    """

    # ADR 0003 s1.1 -- the commitment ramp: lambda is 0 through pick
    # `ramp_start`, then rises linearly over `ramp_span` picks to 1.0.
    # Since ADR 0018 retired openness the ramp shapes only color fit, curve
    # and role.
    #
    # Both are now fitted rather than guessed (ADR 0018): the full-dump
    # backtest wanted a start of 0 and a span of 14, at 23% leverage each,
    # against hand-guesses of 4 and 10. Together they say the pool starts
    # constraining scoring from the very first pick and reaches full force
    # at pick 14 -- the last pick of a HOB pack -- rather than beginning at
    # pick 4 and pinning at the same place. The ramp is gentler early and
    # never flat.
    #
    # `ramp_start` is kept as a tunable even though HOB fitted it to zero:
    # ADR 0013 makes these format-level, and a slower format may well want
    # a pick or two of free speculation before the pool binds.
    ramp_start: int = 0
    ramp_span: int = 14

    # Color fit (ADR 0012, reshaped by ADR 0015). `tax_value` is the
    # commitment tax in pp per **off-color**, at lambda = 1: a mono card in
    # a color with no presence in the pool pays one of these, a three-color
    # card with none of its colors present pays three. It is
    # format-level, because some formats punish three-color soup hard and
    # some barely at all (ADR 0013); 12.0 is HOB's, hand-picked, and the
    # only tunable here with no measured basis.
    #
    # Was 12.0 under ADR 0012, where the unit was a pair-overlap fraction
    # and a mono card could only ever reach half of it. The ceiling in pp is
    # unchanged; what changed is that it is now reached whenever the card's
    # color is absent, rather than only when your two colors are balanced.
    #
    # The full-dump backtest left this at 6.0 (ADR 0018) -- a hand-picked
    # number the fit declined to move, which is the strongest confirmation
    # in the run: 43.5% leverage and the widest loss range of any constant
    # (1.20 to 1.88pp across a 0-24 grid). Color commitment is doing more
    # work than every other conditioning term put together.
    tax_value: float = 6.0

    # ADR 0003 s1.3 -- curve. `target_curve` is how many non-land cards a
    # deck in this format wants at each mana value (7+ counts as 6). Derived
    # from HOB winning decks, not folklore: see docs/target-curve.md.
    # `curve_weight` is deliberately small; curve must not outrank a
    # two-point card-quality difference.
    #
    # Fitted to 0.25 (ADR 0018), down from a guessed 0.75, at the highest
    # leverage of any deck-shape constant (30.4%) and the second-widest
    # loss range in the run. Curve is the one deck-shape term the fit kept:
    # mana value is the thing a card's GIH WR carries no signal about
    # (54.6-56.7 and non-monotone across the curve), so a curve hole is
    # real information rather than a second helping of card quality.
    target_curve: dict[int, int] = field(
        default_factory=lambda: {1: 2, 2: 8, 3: 7, 4: 4, 5: 2, 6: 1}
    )
    curve_weight: float = 0.25

    # ADR 0003 s1.4 -- role, now removal scarcity and nothing else.
    #
    # **The creature branch is gone** (ADR 0018). The fit wanted
    # `creature_weight` at exactly 0.0, from a guess of 0.40, at 20.7%
    # leverage -- measured, not merely unexercised. The reason is
    # double-counting: GIH WR is measured over the real decks that played
    # the card, so it already prices being a creature, which on HOB is
    # worth +2.88pp over the rest of the set (112 creatures, 56.07 vs
    # 53.19). Paying a creature again for being a creature pays twice, and
    # the fit correctly shrank the second payment to nothing.
    #
    # Removal survives the same argument, which is worth stating because it
    # is not obvious. The `_removal_` tag also carries a GIH WR premium
    # (+2.33pp over the rest, on 14 cards), so the double-counting is real
    # there too -- but the fit still wanted a positive weight, just a
    # smaller one: 0.5, down from a guessed 1.25, at 13.1% leverage. The
    # reading is that removal is scarce enough in a 4-card target that
    # *running out* is a genuine fact about your pool, whereas a 14-creature
    # target is so easily met that the creature deficit was firing almost
    # unconditionally. At 0.5 the term no longer outranks a two-point
    # quality gap, which restores ADR 0003 s1.4's cap that ADR 0005 had
    # predicted would need lifting.
    #
    # `target_removal` counts the hand-authored `_removal_` tag, so it is
    # only as complete as the taxonomy and wants re-deriving as more of the
    # set is tagged -- but it is counted the same way on both sides, so
    # partial tagging shrinks the target and the pool count together. The
    # fit confirmed 4 (from docs/target-curve.md's measured 4.2).
    removal_weight: float = 0.5
    target_removal: int = 4

    # ADR 0006 s5 -- synergy. `synergy_weight` is pp per coefficient unit
    # (PLACEHOLDER: the ADR gives no starting value). `synergy_cap` is a
    # loose ceiling on the whole term so several pairs firing at once cannot
    # outweigh a large base or role gap.
    # 0.75 is the first constant in this project fitted rather than guessed:
    # the full-dump backtest wanted exactly this for the marginal form (ADR
    # 0017), having wanted 0.0 for the absolute one. Measured on 132,246
    # picks, validated on a 487,198-pick holdout.
    synergy_weight: float = 0.75
    synergy_cap: float = 5.0
    # Firings below this many pp are counted but never surfaced to the brief.
    synergy_firing_floor: float = 0.1

    # A card under `min_games` is still scored, but carries
    # `insufficient_data` for the UI to annotate.
    min_games: int = 1000

    # ADR 0008 -- classification. The gap to the pack's best card at which a
    # pick stops being `solid` and then stops being `questionable`. Fixed
    # percentage points: no noise floor, no sigma scaling, no absolute
    # floor. `solid_gap` doubles as the spread below which a whole pack is
    # `indifferent`, because that is exactly "every card here is solid".
    solid_gap: float = 2.0
    mistake_gap: float = 4.0

    # ADR 0024 s1 -- the Narrow Pick: the drafter took the pack's only
    # `solid` card while at least `narrow_pick_min_questionable` cards were
    # close behind, in a pack of at least `narrow_pick_min_cards` distinct
    # cards. The questionable condition keeps out "one bomb and chaff":
    # HOB has six packs with a single solid card and none has two
    # questionable ones. PLACEHOLDERS, to tune once real drafts show
    # whether the notes read as cheap or never fire.
    narrow_pick_min_cards: int = 8
    narrow_pick_min_questionable: int = 2


@dataclass(frozen=True)
class Stats:
    """The statistics the terms read, already loaded from the database.

    overall: oracle_id -> (gih_wr, games), the format-wide rate -- the number
    17Lands shows, and since ADR 0012 the only win rate the function reads.

    Archetype-scoped rates are gone. ADR 0003 s1.2 treated them as the
    synergy layer, ADR 0011 corrected them for their archetype's own
    strength, and ADR 0012 removed them: measured across the three reference
    drafts the on-color branch sat on zero (mean +0.075, median 0.00), which
    is card-specific fit plus noise rather than a signal. `card_archetype_stats`
    and `archetype_stats` stay in the database for the prompt brief's sake,
    but nothing in the fitness path reads either.
    """

    format_avg_wr: float
    overall: dict[OracleId, tuple[float, int]] = field(default_factory=dict)

    # There is deliberately no `alsa` here. ALSA was read by one term,
    # openness, and ADR 0018 retired it, so the fitness function no longer
    # consumes ALSA at all. The statistic itself is alive and well: it is
    # still ingested, still stored on `cards`, still shown in the review's
    # card panel and still passed to the prompt brief. It is simply not a
    # scoring input any more -- ALSA says what drafters believe a card is
    # worth, and the fit found no value in that beyond what GIH WR, which
    # says what it is actually worth, already carries.

    def gih_wr(self, oracle_id: OracleId) -> float:
        """The card's format-wide win rate."""
        wr, _ = self.overall.get(oracle_id, (None, 0))
        # A card with no games at all is worth what filler is worth.
        return wr if wr is not None else self.format_avg_wr - 3.0


def commitment(t: int, cfg: FitnessConfig) -> float:
    """How much the pool constrains pick `t` (global index, 1-based).

    0.0 = the pool tells us nothing yet; 1.0 = the pool fully determines
    what is playable. Every lambda-scaled term reads this.
    """
    return min(1.0, max(0.0, (t - cfg.ramp_start) / cfg.ramp_span))


# --------------------------------------------------------------------------
# The predicted archetype, and base: conditioned card quality
# (ADR 0003 s1.2 as revised by BIG_FIX_#1, 2026-09-18)
# --------------------------------------------------------------------------

# The tags several terms key off. `_removal_` is hand-authored and is the only
# thing that counts as removal (BIG_FIX_#1: no oracle-text heuristic);
# `creature` and `land` are derived from the type line by the caller. They sit
# here rather than beside the role term because the color terms read `land`
# too: lands have no curve, are excluded from the archetype floats, and take
# their playable colors from their color identity (ADR 0012 s6).
REMOVAL_TAG = "_removal_"
CREATURE_TAG = "creature"
LAND_TAG = "land"


PIP_RE = re.compile(r"\{([^}]*)\}")


def color_options(mana_cost: str | None, colors: str) -> list[str]:
    """The alternative color sets that can pay a card, as sorted WUBRG strings.

    Round 3 of BIG_FIX_#1: hybrid cards count as dual-monocolored. Scryfall
    marks a {B/R} card as gold ("BR"), but for playability it is a black
    card OR a red card, so its options are ["B", "R"]. A true gold {B}{R}
    card has the single option "BR". Fixed pips are required; each hybrid
    pip may be paid by either of its colors; a two-hybrid ({2/W}) pip is
    payable generically, while a Phyrexian ({B/P}) pip still counts as its
    color, as Limited players treat it.
    Only the front face of a split / adventure cost counts. Options that
    are supersets of another option are dropped, so {1}{B}{B/R} is just
    ["B"]. Without a mana cost, the card's colors are the one option.
    """
    if not mana_cost:
        return ["".join(c for c in "WUBRG" if c in colors)]
    front = mana_cost.split("//")[0]
    required: set[str] = set()
    hybrids: list[set[str]] = []
    for pip in PIP_RE.findall(front):
        letters = {part for part in pip.split("/") if part in "WUBRG" and part}
        if not letters:
            continue  # generic, X, snow
        if "/" in pip and len(letters) == 2:
            hybrids.append(letters)  # {B/R}: either color
        elif "/" in pip and "2" in pip.split("/"):
            continue  # {2/W}: payable generically
        else:
            required |= letters  # {B}; {B/P} is still a black pip
    options: set[frozenset[str]] = set()
    for choice in itertools.product(*hybrids) if hybrids else [()]:
        options.add(frozenset(required | set(choice)))
    minimal = [o for o in options if not any(other < o for other in options)]
    return sorted("".join(c for c in "WUBRG" if c in o) for o in minimal)


def playable_colors(card: dict) -> list[str]:
    """The color sets this card can be played in, as sorted WUBRG strings.

    For a spell this is `color_options(mana_cost, colors)`: what can pay it.
    For a **land** nothing pays it, so the question is which colors it
    serves, and the answer is its **color identity, read as hybrid** -- one
    option per color, so a BR dual land is playable in any pair holding
    black or red (ADR 0012 s6).

    Hybrid rather than gold is the whole point. A `{B}{R}` spell in a BG
    deck is uncastable; Goblin-town in a BG deck taps for black and goes
    straight in. Treating the two alike would be plainly wrong about Magic,
    and it generalizes upward: a WUB tri-land in a UB deck taps for two of
    your colors, so it is more useful than a dual, not less.

    Color *identity* rather than produced mana is deliberate, not a
    convenience. A land whose only relevant ability costs `{B}` is
    black-exclusive in practice even though it taps for nothing colored,
    and identity is what captures that.

    A land with no color identity is playable everywhere, like any
    colorless card.
    """
    if LAND_TAG in (card.get("tags") or ()):
        identity = card.get("color_identity") or ""
        if not identity:
            return [""]
        return [c for c in "WUBRG" if c in identity]
    return color_options(card.get("mana_cost"), card.get("colors") or "")


def playable_in(card: dict, archetype: str) -> bool:
    """A card is playable in a pair if one of its color options fits inside it.

    Colorless cards are playable everywhere; a gold card in exactly one pair;
    a hybrid card in any pair holding either of its colors. Cards without
    `color_options` fall back to their Scryfall colors as the one option.
    """
    options = card.get("color_options") or [card["colors"]]
    return any(set(option) <= set(archetype) for option in options)


# The ten two-color archetypes, in WUBRG order -- the last tie-break when
# two pairs are equally consistent with the pool.
ALL_PAIRS: tuple[str, ...] = (
    "WU",
    "WB",
    "WR",
    "WG",
    "UB",
    "UR",
    "UG",
    "BR",
    "BG",
    "RG",
)


def archetype_floats(pool: list[dict]) -> dict[str, float]:
    """Each pair's share of the pool: how much of what you have it could play.

    ADR 0012. `f_P` is the fraction of the pool's **colored** cards playable
    in pair P. Colorless cards and basic lands are excluded from both the
    numerator and the denominator: an artifact is evidence for no pair in
    particular, and leaving them in the denominator would let a handful of
    late basics quietly buy a discount on straying (the floats are ratios,
    so k colorless cards shrink every gap to `(a_max - a_best) / (n + k)`).

    These are overlap measures, not probabilities: they do not sum to 1. A
    mono-white card counts toward all four W pairs; a gold {W}{R} card
    toward WR alone; a hybrid {W/R} card toward every pair holding W or R,
    because either color alone pays it. That is exactly `playable_in`.

    **Every land is excluded, whatever its colors** (ADR 0012 s6). A dual
    land is evidence that you are open to a pair, not that you are in it,
    and lands are taken for fixing and for lack of anything better. Note
    this is deliberate rather than incidental: Scryfall gives lands no
    color, so the `colors` filter below already dropped them by accident,
    but Magic does print colored lands (Dryad Arbor is a green Land
    Creature) and the exclusion should not depend on that accident.

    Replaces the top-two-by-pick-count rule of ADR 0007 s1, which named one
    pair and returned None on any tie. On the BR reference draft that rule
    scored 21 of 42 picks against RG.
    """
    colored = [c for c in pool if c["colors"] and LAND_TAG not in (c.get("tags") or ())]
    if not colored:
        return {pair: 0.0 for pair in ALL_PAIRS}
    n = len(colored)
    return {
        pair: sum(1 for c in colored if playable_in(c, pair)) / n for pair in ALL_PAIRS
    }


def predicted_archetype(pool: list[dict]) -> str | None:
    """The pair the pool is heading toward: the highest float.

    One definition of "your archetype", shared by the role term, the UI and
    the brief (ADR 0012 s4). None only when no pair can play anything --
    an empty pool, an all-colorless one, or one holding only three-color
    cards. Unlike the rule it replaces it never returns None for a tie.

    Note the fitness tax does not call this: it reads float *values*, so a
    tie is harmless there and needs no tie-break at all. Only the callers
    that must *name* a pair -- the role term, the UI, the brief -- need one.

    Ties are broken by how many pool cards vote for the pair's colors (a
    card votes once per color it has), then by WUBRG order. A pool of one
    {B/R} hybrid and one red card floats BR, WR, UR and RG all at 1.0, but
    black has a vote and white and green do not, so it reads BR. Falling
    straight to WUBRG order would have read WR, which is a worse answer
    than the rule this replaced gave.
    """
    floats = archetype_floats(pool)
    lead = max(floats.values())
    if lead <= 0.0:
        return None
    votes = {c: sum(1 for card in pool if c in card["colors"]) for c in "WUBRG"}
    tied = [pair for pair in ALL_PAIRS if floats[pair] == lead]
    return max(
        tied, key=lambda pair: (votes[pair[0]] + votes[pair[1]], -ALL_PAIRS.index(pair))
    )


def colored_counts(pool: list[dict]) -> dict[str, int]:
    """How many pool cards contain each color. A gold card counts for both.

    Lands are excluded whatever their colors, for the same reason they are
    excluded from the floats (ADR 0012 s6): a dual land says you are open to
    a pair, not that you are in it.
    """
    counts = {c: 0 for c in "WUBRG"}
    for card in pool:
        if LAND_TAG in (card.get("tags") or ()):
            continue
        for color in card["colors"]:
            counts[color] += 1
    return counts


def color_tax_units(card: dict, pool: list[dict]) -> float:
    """How many off-colors' worth of commitment this card asks you to give up.

    ADR 0015. One unit per off-color, each scaled by how far that color is
    from the commitment your *second* color already has:

        units(option) = sum over c in option, c not in A, of
                        clamp(0, 1, (second - counts[c]) / second)

    where A is the predicted archetype and `second` the pool count of its
    weaker color. A mono card in a color with no presence pays a full unit;
    a three-color card with none of its colors present pays three.

    **The minimum is taken over the card's color options, never a sum over
    its colors.** A {2}{B/G} card needs black *or* green, so it pays
    whichever is cheaper. Summing over `colors` would charge Duskwatch
    Hunter for both -- -9.75pp rather than -4.50pp -- on a set where 12 of
    26 multicolor cards are hybrid. Dual lands fall out of the same rule.

    Replaces ADR 0012 s2's pair-overlap gap, which collapsed on a lopsided
    pool: with 8 W and 2 U, WG floats 0.80 against WU's 1.00, so a green
    card paid 2.4pp. The gap was saying "you are basically mono-white, so
    green is nearly as good a second color as blue" -- true, and useless as
    advice. Measuring against the second color's two cards gives the full
    tax instead.

    Clamped below at 0 because the archetype comes from the floats while
    these counts do not, so a color outside A can out-count A's weaker one.
    """
    archetype = predicted_archetype(pool)
    if archetype is None:
        return 0.0
    counts = colored_counts(pool)
    second = min(counts[c] for c in archetype)
    if second <= 0:
        return 0.0  # fewer than two colors in the pool: no commitment to be off
    options = card.get("color_options") or [card["colors"]]
    return min(
        sum(
            min(1.0, max(0.0, (second - counts[color]) / second))
            for color in option
            if color not in archetype
        )
        for option in options
    )


def color_fit(card: dict, pool: list[dict], t: int, cfg: FitnessConfig) -> float:
    """What this card costs in pp for not being what the pool is buying.

        color_fit = -lambda * tax_value * color_tax_units

    Never positive. ADR 0012 made color fit a pure commitment tax: there is
    no reward branch, because there is no longer a conditioned win rate to
    compare against. A card that suits your deck pays nothing; it is not
    paid anything.

    The tax is deliberately self-reinforcing. Every off-color card in the
    pool raises its own colors' floats and dilutes the leader, so a pool of
    10 W, 10 U and 10 G taxes a further green card at exactly 0.00. The view
    taken is that such a pool *is* three colors and the score should say so;
    "you are three colors" is a sentence for the brief, not a tax applied to
    every pick.
    """
    return -commitment(t, cfg) * cfg.tax_value * color_tax_units(card, pool)


# --------------------------------------------------------------------------
# ADR 0003 s1.3 -- curve: marginal curve value
# --------------------------------------------------------------------------


def mv_bucket(cmc: float) -> int:
    """Mana value clamped to 1..6: 0-cost spells sit with the ones, 7+ with the sixes."""
    return int(min(max(cmc, 1), 6))


def curve(card: dict, pool: list[dict], t: int, cfg: FitnessConfig) -> float:
    """Reward filling a hole in the curve; penalize piling on, in pp.

    Only matters once there is a deck shape to disturb, so it scales with the
    ramp. Counts every pool card at the mana value, on or off color: early
    that is right, and late the off-color cards are few. If the backtest
    finds otherwise, count only cards playable in the leading archetype.

    **Lands are excluded on both sides**: a land is not a spell, so it neither
    fills a curve slot nor has a curve of its own. This also matches how
    `target_curve` was derived, which counted non-land cards only
    (docs/target-curve.md). Without it `mv_bucket` would clamp their zero
    mana value up to 1 and draft them as one-drops.
    """
    if LAND_TAG in card["tags"]:
        return 0.0
    lam = commitment(t, cfg)
    mv = mv_bucket(card["cmc"])
    have = sum(
        1 for c in pool if LAND_TAG not in c["tags"] and mv_bucket(c["cmc"]) == mv
    )
    want = cfg.target_curve[mv]
    if have < want:
        return cfg.curve_weight * lam  # fills a hole
    excess = have - want
    return -cfg.curve_weight * lam * min(1.0, excess / 2)  # piling on


# --------------------------------------------------------------------------
# ADR 0003 s1.4 -- role: removal / creature scarcity
# --------------------------------------------------------------------------


def on_color_pool(pool: list[dict]) -> list[dict]:
    """The pool cards that count toward deck-shape terms.

    Once an archetype is predicted, only cards playable in it (colorless
    included); before that, every card, because nothing is off-color yet.
    Copies are separate entries, so two of the same creature are two.

    Reads the same leading pair the rest of the function does (ADR 0012 s4).
    Under the rule this replaced, a momentary tie for second place collapsed
    the archetype to None and silently counted the whole pool -- including
    its off-color half -- toward the creature and removal targets.
    """
    archetype = predicted_archetype(pool)
    if archetype is None:
        return list(pool)
    return [c for c in pool if playable_in(c, archetype)]


def role(card: dict, pool: list[dict], t: int, cfg: FitnessConfig) -> float:
    """Reward a removal spell while the pool is short of removal, in pp.

    Same shape as curve, scaled by the ramp. The deficit saturates -- two
    removal spells short already pays in full -- so a bare pool does not
    make every removal spell look like a bomb. Removal is the `_removal_`
    tag and nothing else, so that non-traditional but real removal can be
    declared as such by hand. Only on-color pool cards count (BIG_FIX_#1).

    **One branch, not two** (ADR 0018). This term used to pay creatures as
    well, on the argument that a body is worth about a third of a removal
    spell. The backtest zeroed `creature_weight` at 20.7% leverage: a
    card's GIH WR is measured over the decks that really played it, so it
    already prices being a creature (+2.88pp on HOB), and a 14-creature
    target against a saturating deficit meant the branch fired on nearly
    every creature nearly unconditionally -- a flat second helping of
    something `base` had already paid for. Removal survived because a
    4-card target is scarce enough that running out is a real property of
    your pool rather than a restatement of card quality.

    Note that a creature which is *also* tagged `_removal_` still scores
    here, as it should: what was retired is the reward for being a body,
    not the reward for being removal that happens to have a body.
    """
    if REMOVAL_TAG not in card["tags"]:
        return 0.0
    counted = on_color_pool(pool)
    deficit = max(
        0, cfg.target_removal - sum(1 for c in counted if REMOVAL_TAG in c["tags"])
    )
    return cfg.removal_weight * commitment(t, cfg) * min(1.0, deficit / 2)


# --------------------------------------------------------------------------
# ADR 0006 -- synergy: tag pairs against the pool
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SynergyFiring:
    """One authored tag pair that found its complement in the pool."""

    tag_on_card: str
    complementary_tag: str
    pool_count: int  # n: copies of the complementary tag in the pool
    effective_count: float  # n_eff: n after the edge's saturation curve
    coefficient: float
    pp: float
    # What this card USUALLY finds for this edge, in n_eff (ADR 0017). The
    # firing is worth `coefficient * (effective_count - expected_count)`, so
    # a pool that is merely typical pays nothing and a pool missing the
    # complement entirely pays a penalty. Zero without a baseline loaded, in
    # which case the term reverts to ADR 0006's absolute form.
    expected_count: float = 0.0
    # Which pool cards carry `complementary_tag`, so a brief can name them
    # rather than leave an LLM to guess (BoosterTutor #22). In pool order,
    # which is pick order, with duplicates kept -- copies are real copies,
    # so `len(contributing_oracle_ids) == pool_count` always.
    #
    # **Deliberately a flat list, with no per-card weighting.** The decay
    # curve prices the *Nth copy*, not the Nth card: it says a sixth sac
    # outlet adds almost nothing, never that one particular outlet is the
    # important one. Distributing `1, 0.5, 0.25, ...` across these ids by
    # pick order would manufacture a ranking the arithmetic does not
    # express, and pick order is not importance. The honest aggregate --
    # how much the whole firing is worth however many copies there are --
    # is already in `effective_count` and `pp`.
    contributing_oracle_ids: tuple[OracleId, ...] = ()


@dataclass(frozen=True)
class SynergyResult:
    total: float  # capped per ADR 0006 s5
    top_firings: list[SynergyFiring]  # at most two, each at or above the floor


def effective_count(n: int, decay: float) -> float:
    """ADR 0009: each further copy of the complementary tag is worth `decay` of the last.

        n_eff = 1 + d + d^2 + ... + d^(n-1) = (1 - d^n) / (1 - d)

    So the first copy always pays the edge's full coefficient and later ones
    taper. At d = 1 nothing decays and n_eff is just n, the behavior ADR
    0006's uncapped edges had. At d = 0.5 the series runs 1, 1.5, 1.75,
    1.875, converging on 2. At d = 0 only the first copy counts at all, so a
    second enabler adds nothing.

    This replaces ADR 0006 s4's `cap` curve, which taxed even the first copy
    (at cap = 2 it was worth 0.67) and could not express "no decay".
    """
    if n <= 0:
        return 0.0
    if decay >= 1.0:
        return float(n)
    return (1.0 - decay**n) / (1.0 - decay)


def synergy(
    card: dict,
    pool: list[dict],
    edges: list[dict],
    cfg: FitnessConfig,
    *,
    pack_no: int = 1,
    baseline: dict[tuple[OracleId, int, str, str, str], float] | None = None,
) -> SynergyResult:
    """Credit for tagged game-plans the pool has already committed to, in pp.

    Walks only the authored `tag_pairs` rows (`edges`: dicts with enabler,
    payoff, coefficient, decay). Each edge touching a tag on the card is read
    once, from whichever end the card is on: an enabler candidate counts
    payoffs in the pool, a payoff candidate counts enablers. No transitivity,
    no imputed reverse edge. Copies count, so a self-payoff (enabler ==
    payoff) falls out of the same rule. Not scaled by the ramp: two tagged
    cards sharing a pool have already resolved their own uncertainty.

    Each firing carries the pool cards that fired it, so the brief can name
    them; see `SynergyFiring.contributing_oracle_ids` for why they are not
    individually weighted.

    **With a `baseline` loaded the term measures a margin** (ADR 0017): each
    firing is worth `coefficient x (n_eff - E[n_eff | card, pack, edge])`, so
    a typical pool pays nothing, an unusually rich one pays a bonus, and one
    missing the complement altogether pays a penalty. An empty baseline
    leaves ADR 0006's absolute behaviour untouched, which is what every test
    written before ADR 0017 still exercises.

    Note `top_firings` still filters on `synergy_firing_floor`, so only
    positive contributions reach the brief. Surfacing the *worst* firing is
    a brief question (BoosterTutor #22), not a scoring one.
    """
    tags = card["tags"]
    expected = baseline or {}
    oracle_id = card["oracle_id"]
    firings: list[SynergyFiring] = []
    for e in edges:
        for tag_on_card, complementary in (
            (e["enabler"], e["payoff"]),
            (e["payoff"], e["enabler"]),
        ):
            if tag_on_card not in tags:
                continue
            contributors = tuple(
                c["oracle_id"] for c in pool if complementary in c["tags"]
            )
            n = len(contributors)
            n_eff = effective_count(n, e["decay"])
            usual = expected.get(
                (oracle_id, pack_no, e["enabler"], e["payoff"], tag_on_card), 0.0
            )
            if n == 0 and usual == 0.0:
                # Nothing fired and nothing was expected: no contribution
                # either way. Without this the loop would manufacture a
                # zero-valued firing for every edge the card can reach.
                if e["enabler"] == e["payoff"]:
                    break
                continue
            firings.append(
                SynergyFiring(
                    tag_on_card,
                    complementary,
                    n,
                    n_eff,
                    e["coefficient"],
                    pp=cfg.synergy_weight * e["coefficient"] * (n_eff - usual),
                    contributing_oracle_ids=contributors,
                    expected_count=usual,
                )
            )
            if e["enabler"] == e["payoff"]:
                break  # the diagonal: both ends are the same read, count it once
    total = min(cfg.synergy_cap, sum(fr.pp for fr in firings))
    top = sorted(
        (fr for fr in firings if fr.pp >= cfg.synergy_firing_floor),
        key=lambda fr: -fr.pp,
    )[:2]
    return SynergyResult(total=total, top_firings=top)


# --------------------------------------------------------------------------
# ADR 0003 s1.6 -- the decomposition is the output
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CardFitness:
    """One card's fitness to one pool at one pick, in pp, with the reasons.

    `color_fit` is the commitment tax: what the card costs for not being
    what the pool is buying (ADR 0012). It is never positive. It is still
    the sentence a coach wants to write ("not a card-quality mistake, a
    color-commitment one"). The parts sum to `total`.

    There is no `openness` part any more (ADR 0018). Anything that
    enumerates these fields must list four conditioning terms, not five.
    """

    oracle_id: OracleId
    total: float
    base_unconditioned: float  # the overall GIH WR -- the number 17Lands shows
    color_fit: float  # -lambda * tax_value * color_tax_fraction, <= 0
    curve: float
    role: float  # removal scarcity only, since ADR 0018
    synergy: float
    n_games: int  # sample size behind the win rate
    top_firings: list[SynergyFiring]
    insufficient_data: bool  # under min_games; scored anyway, annotated in the UI


def score_pack(
    pack: list[dict],
    pool: list[dict],
    t: int,
    pack_no: int,
    stats: Stats,
    edges: list[dict],
    cfg: FitnessConfig,
    baseline: dict[tuple[OracleId, int, str, str, str], float] | None = None,
) -> list[CardFitness]:
    """Score every card in a pack against the pool before this pick.

    `t` is the global pick index (1-based across the draft) and `pack_no`
    the pack (1-based, read by the synergy baseline); `edges` are the
    authored tag_pairs rows and `baseline` the synergy expectations (ADR
    0017), empty for the absolute behaviour of ADR 0006.
    Order of the result matches `pack`.

    **There is no `pick` argument any more** (ADR 0018). The position
    within the pack was read by exactly one term, openness, and retiring it
    left the parameter dead. `t` and `pack_no` between them still say
    everything the surviving terms need to know about where in the draft
    this pick sits.
    """
    scored = []
    for c in pack:
        unconditioned = stats.gih_wr(c["oracle_id"])
        _, n_games = stats.overall.get(c["oracle_id"], (None, 0))
        syn = synergy(c, pool, edges, cfg, pack_no=pack_no, baseline=baseline)
        terms = {
            "color_fit": color_fit(c, pool, t, cfg),
            "curve": curve(c, pool, t, cfg),
            "role": role(c, pool, t, cfg),
        }
        scored.append(
            CardFitness(
                oracle_id=c["oracle_id"],
                total=unconditioned + syn.total + sum(terms.values()),
                base_unconditioned=unconditioned,
                synergy=syn.total,
                n_games=n_games,
                top_firings=syn.top_firings,
                insufficient_data=n_games < cfg.min_games,
                **terms,
            )
        )
    return scored


# --------------------------------------------------------------------------
# ADR 0008 -- classification: how conducive was this pick to a winning deck?
# --------------------------------------------------------------------------


def classify_pack(scored: list[CardFitness], cfg: FitnessConfig) -> dict[OracleId, str]:
    """oracle_id -> `solid` / `questionable` / `mistake`, by gap to the pack's best.

    The highest-fitness card in the pack is the gold standard and every
    other card is classed by how far short of it they fall:

        solid         gap <= solid_gap     -- cost little or no equity
        questionable  gap <= mistake_gap   -- a real inaccuracy
        mistake       beyond               -- earns a written note

    Fixed thresholds in pp, nothing else. ADR 0008 retired the noise floor,
    the sigma scaling and the format-average floor: a card with 200 games is
    banded exactly like one with 20,000, and the best card in a weak pack is
    `solid`, because taking it is the most conducive thing on offer.
    """
    best = max(cf.total for cf in scored)
    classes = {}
    for cf in scored:
        gap = best - cf.total
        if gap <= cfg.solid_gap:
            classes[cf.oracle_id] = "solid"
        elif gap <= cfg.mistake_gap:
            classes[cf.oracle_id] = "questionable"
        else:
            classes[cf.oracle_id] = "mistake"
    return classes


def is_indifferent(
    scored: list[CardFitness], cfg: FitnessConfig, *, pack_size: int | None = None
) -> bool:
    """True when no choice in this pack moves the deck.

    Three cases: the pack holds one card (`pack_size`, which can exceed the
    number scored because basic lands are never scored), nothing in it is
    scorable at all, or **every card is solid** -- the spread from best to
    worst is within `solid_gap`, so by the classifier's own definition no
    available pick costs equity.

    ADR 0008 dropped every veto BIG_FIX_#1 and #2 had added, so two equal
    bombs at P1P1 are now `indifferent` rather than several solid picks.
    """
    if (pack_size if pack_size is not None else len(scored)) == 1:
        return True
    if not scored:
        return True
    totals = [cf.total for cf in scored]
    return max(totals) - min(totals) <= cfg.solid_gap


def verdict(
    scored: list[CardFitness],
    taken_oracle_id: OracleId,
    cfg: FitnessConfig,
    *,
    pack_size: int | None = None,
) -> str:
    """The class of the card taken, or `indifferent`.

    Taking a card that was never scored -- a basic land -- is a `mistake`,
    and that is checked *before* the indifferent test. Otherwise a pack of
    one playable and a Swamp would read `indifferent` on a spread of zero,
    and taking the Swamp would come out free.
    """
    if (pack_size if pack_size is not None else len(scored)) == 1:
        return "indifferent"
    if taken_oracle_id not in {cf.oracle_id for cf in scored}:
        return "mistake"
    if is_indifferent(scored, cfg, pack_size=pack_size):
        return "indifferent"
    return classify_pack(scored, cfg)[taken_oracle_id]


def is_narrow_pick(
    scored: list[CardFitness],
    taken_oracle_id: OracleId,
    cfg: FitnessConfig,
    *,
    pack_size: int | None = None,
) -> bool:
    """True when the drafter found the one right answer among tempting ones (ADR 0024).

    The pack held at least `narrow_pick_min_cards` distinct cards
    (`pack_size`, which counts basic lands that were never scored), exactly
    one of them `solid`, at least `narrow_pick_min_questionable` of them
    `questionable`, and the drafter took the `solid` one.
    """
    if (
        pack_size if pack_size is not None else len(scored)
    ) < cfg.narrow_pick_min_cards:
        return False
    if not scored:
        return False
    classes = classify_pack(scored, cfg)
    solid = [oid for oid, c in classes.items() if c == "solid"]
    questionable = sum(1 for c in classes.values() if c == "questionable")
    return (
        solid == [taken_oracle_id] and questionable >= cfg.narrow_pick_min_questionable
    )


def is_noted(verdict_: str, *, narrow: bool) -> bool:
    """A Noted Pick earns a Pick Note: `questionable`, `mistake` or Narrow (ADR 0024).

    Critical notes explain what a pick cost; a Narrow Pick's note gives
    credit for the hard right answer. Everything else is stated, not
    explained, and a draft with no notes at all is a valid outcome. This
    replaces ADR 0008 s3's "only a mistake earns a note".
    """
    return narrow or verdict_ in ("questionable", "mistake")
