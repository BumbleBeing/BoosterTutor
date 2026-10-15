"""Tests for the pick-fitness function, ported from DraftDouble with it.

Every function under test is pure: tiny hand-built cards, pools and stats,
with expected values taken from the ADRs' worked examples rather than
recomputed the way the code computes them.

    ADR 0003 s1   base / curve / role, the commitment ramp, CardFitness
    ADR 0005      fitness classes, verdicts, option value
    ADR 0006      the tag-synergy term
    ADR 0018      openness retired, role's creature branch deleted, the
                  ramp / curve / removal constants fitted
"""

import pytest

from boostertutor.analysis import fitness as f


def card(
    oracle_id: str, *, colors: str = "R", cmc: float = 2.0, tags: tuple[str, ...] = ()
) -> dict:
    """The slice of a card row the fitness function reads."""
    return {"oracle_id": oracle_id, "colors": colors, "cmc": cmc, "tags": list(tags)}


def stats(*, format_avg: float = 56.0, overall: dict | None = None) -> f.Stats:
    """Hand-built statistics. `overall` is oracle_id -> (gih_wr, games).

    Archetype-scoped rates are gone since ADR 0012; the overall rate is the
    only win rate the function reads.
    """
    return f.Stats(format_avg_wr=format_avg, overall=overall or {})


P1P1 = 1


# --------------------------------------------------------------------------
# ADR 0003 s1.1 -- the commitment ramp
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "t, expected",
    [
        (0, 0.0),  # the ramp's foot, which no real pick index reaches
        (1, 1 / 14),  # P1P1 already carries a little pool, since ramp_start = 0
        (7, 0.5),  # halfway up the 14-pick ramp
        (14, 1.0),  # the last pick of pack 1: pinned from here on
        (22, 1.0),
        (42, 1.0),  # last pick of a HOB draft
    ],
)
def test_commitment_ramp_is_linear_then_pinned(t, expected):
    """ADR 0018 fitted the ramp: start 0 (from 4), span 14 (from 10).

    There is no flat stretch any more. The fitted ramp still pins at pick
    14, the last pick of a HOB pack, but it rises from the very first pick
    rather than sitting at zero for four, so the pool starts constraining
    scoring immediately and does so more gently.
    """
    assert f.commitment(t, f.FitnessConfig()) == pytest.approx(expected)


def test_commitment_ramp_still_honours_a_non_zero_start():
    """`ramp_start` survived the fit as a tunable, so it must still work.

    HOB fitted it to zero, but ADR 0013 makes these format-level and a
    slower format may want some picks of free speculation first.
    """
    cfg = f.FitnessConfig(ramp_start=4, ramp_span=10)
    assert f.commitment(4, cfg) == pytest.approx(0.0)
    assert f.commitment(9, cfg) == pytest.approx(0.5)
    assert f.commitment(14, cfg) == pytest.approx(1.0)


# --------------------------------------------------------------------------
# ADR 0012 -- archetype floats and the commitment tax
# --------------------------------------------------------------------------


def pool_of(*specs: str) -> list[dict]:
    """A pool from a list of color strings: pool_of("W", "W", "BR")."""
    return [card(f"c{i}", colors=c) for i, c in enumerate(specs)]


# The ADR 0012 worked example: 4 white, 4 blue, 1 red, 1 red-white, 10 cards.
WORKED_EXAMPLE = pool_of(*(["W"] * 4 + ["U"] * 4 + ["R"] + ["WR"]))
WORKED_FLOATS = {
    "WU": 0.8,
    "WB": 0.4,
    "WR": 0.6,
    "WG": 0.4,
    "UB": 0.4,
    "UR": 0.5,
    "UG": 0.4,
    "BR": 0.1,
    "BG": 0.0,
    "RG": 0.1,
}


def heavy_br_pool(n: int = 20) -> list[dict]:
    """A pool of BR gold cards: BR is the only pair that can play any of it."""
    return [card(f"br{i}", colors="BR") for i in range(n)]


def heavy_br_stats(**extra_overall) -> f.Stats:
    overall = {f"br{i}": (60.0, 5000) for i in range(20)}
    overall.update(extra_overall)
    return stats(format_avg=56.0, overall=overall)


PINNED = 14  # lambda = 1.0 from the last pick of pack 1 on
TAX = f.FitnessConfig().tax_value  # 12.0


def test_archetype_floats_are_each_pairs_share_of_the_pool():
    """ADR 0012's worked example, all ten pairs.

    A mono-white card counts toward all four W pairs; the gold {W}{R} card
    toward WR alone, which is why WU is 0.8 and not 0.9.
    """
    got = f.archetype_floats(WORKED_EXAMPLE)
    assert {k: round(v, 10) for k, v in got.items()} == WORKED_FLOATS


def test_archetype_floats_ignore_colorless_cards_and_basic_lands():
    """Colorless cards leave both sides of the ratio, so they cannot dilute the tax.

    Floats are ratios: leaving k colorless cards in the denominator would
    shrink every gap to (a_max - a_best) / (n + k), and a handful of late
    basics would quietly buy a discount on straying.
    """
    padded = WORKED_EXAMPLE + pool_of("", "", "", "", "")
    assert f.archetype_floats(padded) == f.archetype_floats(WORKED_EXAMPLE)


def test_a_hybrid_card_counts_toward_every_pair_holding_either_color():
    """{B/R} is a black card OR a red one, so it is a full card for both."""
    hybrid = {**card("h", colors="BR"), "color_options": ["B", "R"]}
    floats = f.archetype_floats([hybrid])
    assert floats["WB"] == 1.0 and floats["RG"] == 1.0 and floats["BR"] == 1.0
    assert floats["WU"] == 0.0


def land(oracle_id: str, identity: str) -> dict:
    """A land: no colors of its own, a color identity, and the `land` tag.

    `color_options` is precomputed here exactly as `_fitness_card` does it in
    the ingest -- `playable_in` reads that field rather than deriving options
    per call, so a fixture that omits it would silently read as colorless.
    """
    base = dict(card(oracle_id, colors=""), color_identity=identity, tags=["land"])
    return {**base, "color_options": f.playable_colors(base)}


def test_a_dual_land_is_playable_in_any_pair_holding_either_of_its_colors():
    """Hybrid, not gold (ADR 0012 s6): Goblin-town in a BG deck taps for black."""
    goblin_town = land("gt", "BR")
    assert f.playable_colors(goblin_town) == ["B", "R"]
    assert f.playable_in(goblin_town, "BR") and f.playable_in(goblin_town, "BG")
    assert f.playable_in(goblin_town, "UR") and not f.playable_in(goblin_town, "WU")


@pytest.mark.parametrize(
    "identity, expected",
    [
        ("BR", ["B", "R"]),  # dual
        ("R", ["R"]),  # a mono-colored nonbasic land
        (
            "WUB",
            ["W", "U", "B"],
        ),  # a tri-land taps for three, so it suits more decks, not fewer
        ("", [""]),  # colorless: playable anywhere
    ],
)
def test_a_lands_playable_colors_come_from_its_color_identity(identity, expected):
    assert f.playable_colors(land("x", identity)) == expected


def test_a_lands_identity_counts_even_when_it_taps_for_nothing_colored():
    """Deliberate: a land whose only ability costs {B} is black-exclusive in practice."""
    utility = land("u", "B")  # taps for colorless, activates for {B}
    assert f.playable_colors(utility) == ["B"]
    assert not f.playable_in(utility, "WU")


def test_a_spell_is_unaffected_by_its_color_identity():
    """`playable_colors` defers to the mana cost for anything that is not a land."""
    spell = dict(card("s", colors="BR"), color_identity="BR", mana_cost="{2}{B/R}")
    assert f.playable_colors(spell) == ["B", "R"]
    gold = dict(card("g", colors="BR"), color_identity="BR", mana_cost="{B}{R}")
    assert f.playable_colors(gold) == ["BR"]


def test_an_off_color_dual_land_pays_only_its_cheaper_color():
    """Its identity is read as hybrid (ADR 0012 s6), so the sum takes the minimum."""
    balanced = pool_of(*(["W"] * 8 + ["U"] * 8))
    cfg = f.FitnessConfig()
    assert f.color_fit(land("gt", "BR"), balanced, PINNED, cfg) == pytest.approx(-TAX)
    assert f.color_fit(land("lt", "WU"), balanced, PINNED, cfg) == pytest.approx(0.0)
    assert f.color_fit(land("wild", ""), balanced, PINNED, cfg) == pytest.approx(0.0)


def test_every_land_is_excluded_from_the_archetype_floats():
    """A dual land says you are open to a pair, not that you are in it (ADR 0012 s6)."""
    spells = pool_of("W", "W", "U")
    assert f.archetype_floats(spells + [land("gt", "BR")]) == f.archetype_floats(spells)
    # Explicitly, not by accident of Scryfall giving lands no color: Magic
    # prints colored lands, and Dryad Arbor must not vote either.
    arbor = dict(
        card("arbor", colors="G"), color_identity="G", tags=["land", "creature"]
    )
    assert f.archetype_floats(spells + [arbor]) == f.archetype_floats(spells)


def test_a_pool_of_only_lands_predicts_no_archetype():
    assert f.predicted_archetype([land("a", "BR"), land("b", "WU")]) is None


def test_predicted_archetype_is_the_pair_with_the_highest_float():
    assert f.predicted_archetype(WORKED_EXAMPLE) == "WU"
    assert f.predicted_archetype(heavy_br_pool()) == "BR"


def test_predicted_archetype_breaks_a_tie_in_wubrg_order_rather_than_giving_up():
    """One white card is equally consistent with all four W pairs; name one.

    The rule this replaced returned None on any tie, which zeroed color fit
    for a whole pack every time second and third place touched.
    """
    assert f.predicted_archetype(pool_of("W")) == "WU"
    assert f.predicted_archetype(pool_of("R")) == "WR"


def test_predicted_archetype_is_none_only_when_no_pair_can_play_anything():
    assert f.predicted_archetype([]) is None
    assert f.predicted_archetype(pool_of("", "")) is None  # all colorless
    assert f.predicted_archetype(pool_of("WUB")) is None  # three colors


def test_color_fit_is_zero_for_a_card_in_the_leading_pair():
    cfg = f.FitnessConfig()
    for colors in ("W", "U", "WU", ""):
        c = card("x", colors=colors)
        assert f.color_fit(c, WORKED_EXAMPLE, PINNED, cfg) == pytest.approx(0.0)


def test_color_fit_charges_one_unit_per_off_color_against_the_second_colors_count():
    """ADR 0015. The example pool leads WU, whose weaker color (U) has 4 cards.

    Red is on two of them -- the mono-red card and the WR gold card, which
    counts for both its colors -- so it sits halfway to that commitment.
    Green has none, so it pays a whole unit.
    """
    cfg = f.FitnessConfig()
    assert f.color_tax_units(card("g", colors="G"), WORKED_EXAMPLE) == pytest.approx(
        1.0
    )
    assert f.color_tax_units(card("r", colors="R"), WORKED_EXAMPLE) == pytest.approx(
        0.5
    )
    assert f.color_fit(
        card("g", colors="G"), WORKED_EXAMPLE, PINNED, cfg
    ) == pytest.approx(-TAX)
    assert f.color_fit(
        card("r", colors="R"), WORKED_EXAMPLE, PINNED, cfg
    ) == pytest.approx(-0.5 * TAX)


def test_off_colors_add_but_a_hybrid_pays_only_its_cheaper_one():
    """The minimum is over color options, never a sum over `colors`.

    A {2}{B/G} card needs black *or* green. Summing would charge it for both
    -- the defect that would have taken Duskwatch Hunter from -4.50 to
    -9.75pp on a set where 12 of 26 multicolor cards are hybrid.
    """
    cfg = f.FitnessConfig()
    gold = dict(card("gold", colors="BG"), color_options=["BG"])
    hybrid_bg = dict(card("hyb", colors="BG"), color_options=["B", "G"])
    assert f.color_tax_units(gold, WORKED_EXAMPLE) == pytest.approx(2.0)
    assert f.color_tax_units(hybrid_bg, WORKED_EXAMPLE) == pytest.approx(1.0)
    assert f.color_fit(gold, WORKED_EXAMPLE, PINNED, cfg) == pytest.approx(-2 * TAX)
    assert f.color_fit(hybrid_bg, WORKED_EXAMPLE, PINNED, cfg) == pytest.approx(-TAX)


def test_a_three_color_card_pays_three_units_when_none_of_its_colors_are_present():
    """Thranduil, the Elvenking ({2}{B}{G}{U}) is HOB's only three-color card."""
    wr_pool = pool_of(*(["W"] * 6 + ["R"] * 4))
    thranduil = dict(card("t", colors="UBG"), color_options=["UBG"])
    assert f.color_tax_units(thranduil, wr_pool) == pytest.approx(3.0)
    assert f.color_fit(thranduil, wr_pool, PINNED, f.FitnessConfig()) == pytest.approx(
        -3 * TAX
    )


def test_color_fit_is_the_whole_tax_when_the_pool_can_play_none_of_the_card():
    """A blue card against a pool of BR gold cards: no pair holding U plays anything."""
    blue = card("u", colors="U")
    assert f.color_fit(
        blue, heavy_br_pool(), PINNED, f.FitnessConfig()
    ) == pytest.approx(-TAX)


def test_a_card_in_three_absent_colors_pays_three_whole_units():
    """A UB pool shares none of WRG, so all three colors are charged."""
    ub_pool = pool_of(*(["U"] * 10 + ["B"] * 10))
    naya = dict(card("n", colors="WRG"), color_options=["WRG"])
    assert f.color_tax_units(naya, ub_pool) == pytest.approx(3.0)
    assert f.color_fit(naya, ub_pool, PINNED, f.FitnessConfig()) == pytest.approx(
        -3 * TAX
    )


def test_color_fit_is_small_at_p1p1_and_scales_with_the_commitment_ramp():
    """ADR 0018's fitted ramp starts at 0, so P1P1 charges 1/14 of the tax.

    That is -0.43pp on a fully collapsed pool, against a `solid_gap` of
    2.0: enough to break a tie toward your colors at the very first pick,
    nowhere near enough to outrank a real quality difference.
    """
    blue, cfg = card("u", colors="U"), f.FitnessConfig()
    assert f.color_fit(blue, heavy_br_pool(), P1P1, cfg) == pytest.approx(-TAX / 14)
    early, mid, late = (
        f.color_fit(blue, heavy_br_pool(), t, cfg) for t in (5, 9, PINNED)
    )
    assert 0.0 > early > mid > late == pytest.approx(-TAX)


def test_color_fit_is_never_positive():
    cfg = f.FitnessConfig()
    for colors in ("W", "U", "B", "R", "G", "WU", "BG", "", "WUB"):
        c = card("x", colors=colors)
        for t in (1, 5, 9, PINNED, 42):
            assert f.color_fit(c, WORKED_EXAMPLE, t, cfg) <= 0.0


def test_an_empty_pool_taxes_nothing_and_does_not_divide_by_zero():
    cfg = f.FitnessConfig()
    assert f.color_fit(card("g", colors="G"), [], PINNED, cfg) == pytest.approx(0.0)
    assert f.color_fit(
        card("g", colors="G"), pool_of("", ""), PINNED, cfg
    ) == pytest.approx(0.0)


def test_a_lopsided_pool_no_longer_softens_the_tax():
    """The defect ADR 0015 fixes.

    Under the pair-overlap gap an 8W/2U pool floated WG at 0.80 against WU's
    1.00, so green paid a fifth of the tax -- "you are basically mono-white,
    so green is nearly as good a second color as blue". Measured against the
    second color's two cards instead, green pays in full either way.
    """
    cfg = f.FitnessConfig()
    green = card("g", colors="G")
    for pool in (
        pool_of(*(["W"] * 10 + ["U"] * 10)),
        pool_of(*(["W"] * 8 + ["U"] * 2)),
    ):
        assert f.color_fit(green, pool, PINNED, cfg) == pytest.approx(-TAX)


def test_the_tax_falls_as_the_pool_itself_drifts_off_color():
    """Deliberate, and carried over from ADR 0012: a pool that really is
    three colors is three colors.

    Each green card raises green's own count toward the second color's, so
    the next green card is cheaper -- reaching zero when they tie.
    """
    cfg = f.FitnessConfig()
    green = card("g", colors="G")
    taxes = [
        f.color_fit(green, pool_of(*(["W"] * 10 + ["U"] * 10 + ["G"] * g)), PINNED, cfg)
        for g in (0, 2, 4, 6, 8, 10)
    ]
    assert taxes == pytest.approx([-6.0, -4.8, -3.6, -2.4, -1.2, 0.0])
    assert taxes == sorted(taxes)  # monotonically cheaper


def test_lands_are_left_out_of_the_color_counts():
    """Same reason they are left out of the floats (ADR 0012 s6)."""
    spells = pool_of(*(["W"] * 8 + ["U"] * 4))
    with_land = spells + [land("gt", "BR")]
    cfg = f.FitnessConfig()
    assert f.colored_counts(with_land) == f.colored_counts(spells)
    green = card("g", colors="G")
    assert f.color_fit(green, with_land, PINNED, cfg) == pytest.approx(
        f.color_fit(green, spells, PINNED, cfg)
    )


# --------------------------------------------------------------------------
# ADR 0003 s1.3 -- curve: marginal curve value
# --------------------------------------------------------------------------
# target_curve is derived from HOB winning decks (docs/target-curve.md):
# {1: 2, 2: 8, 3: 7, 4: 4, 5: 2, 6: 1}. curve_weight is 0.25pp, fitted by
# the full-dump backtest (ADR 0018) from a guessed 0.75 -- the highest
# leverage of any deck-shape constant, and the one deck-shape term the fit
# kept, because mana value is the thing GIH WR carries no signal about.


def two_drops(n: int) -> list[dict]:
    return [card(f"two{i}", cmc=2.0) for i in range(n)]


def test_curve_rewards_filling_a_hole_by_the_full_weight_once_pinned():
    assert f.curve(
        card("x", cmc=2.0), two_drops(3), PINNED, f.FitnessConfig()
    ) == pytest.approx(0.25)


@pytest.mark.parametrize(
    "have, expected",
    [
        (8, 0.0),  # exactly at target: neither a hole nor a pile
        (9, -0.125),  # one over: half the weight
        (10, -0.25),  # two over: the full weight, and no worse beyond
        (13, -0.25),
    ],
)
def test_curve_penalizes_piling_on_up_to_the_full_weight(have, expected):
    assert f.curve(
        card("x", cmc=2.0), two_drops(have), PINNED, f.FitnessConfig()
    ) == pytest.approx(expected)


def test_curve_scales_with_the_commitment_ramp():
    """Pick 7 is halfway up the fitted 14-pick ramp, so it pays half."""
    cfg = f.FitnessConfig()
    assert f.curve(card("x", cmc=2.0), [], 7, cfg) == pytest.approx(0.125)
    assert f.curve(card("x", cmc=2.0), [], PINNED, cfg) == pytest.approx(0.25)


def test_curve_is_a_fraction_of_a_point_at_the_first_pick():
    """ADR 0018's ramp starts at 0, so P1P1 is no longer exactly nothing.

    It is 1/14 of the weight -- 0.018pp against a `solid_gap` of 2.0, which
    is why the fitted ramp costs nothing in readability at the first pick.
    """
    assert f.curve(card("x", cmc=2.0), [], P1P1, f.FitnessConfig()) == pytest.approx(
        0.25 / 14
    )


def test_curve_buckets_seven_plus_drops_with_the_sixes():
    pool = [card("big", cmc=6.0)]  # target for 6+ is 1: already met
    assert f.curve(
        card("x", cmc=7.0), pool, PINNED, f.FitnessConfig()
    ) == pytest.approx(0.0)


# --------------------------------------------------------------------------
# ADR 0003 s1.4 -- role: removal / creature scarcity
# --------------------------------------------------------------------------
# removal_weight is 0.5pp, fitted by the full-dump backtest (ADR 0018) from
# a guessed 1.25. The deficit saturates at 2 removal spells short. Removal is
# the hand-authored `_removal_` tag and nothing else. Only on-color pool
# cards count once an archetype is predicted, and copies count (BIG_FIX_#1).
#
# **There is no creature branch** (ADR 0018). The fit wanted
# `creature_weight = 0.0` at 20.7% leverage, because a card's GIH WR already
# prices being a creature (+2.88pp on HOB) and a 14-creature target was met
# so easily that the branch fired almost unconditionally.


def removal(n: int) -> list[dict]:
    return [card(f"kill{i}", tags=("_removal_",)) for i in range(n)]


def creatures(n: int) -> list[dict]:
    return [card(f"dude{i}", tags=("creature",)) for i in range(n)]


def test_role_pays_the_full_weight_for_removal_when_the_pool_has_none():
    cfg = f.FitnessConfig(target_removal=4)
    assert f.role(card("x", tags=("_removal_",)), [], PINNED, cfg) == pytest.approx(0.5)


def test_role_pays_half_when_one_removal_spell_short():
    cfg = f.FitnessConfig(target_removal=4)
    assert f.role(
        card("x", tags=("_removal_",)), removal(3), PINNED, cfg
    ) == pytest.approx(0.25)


def test_role_pays_nothing_once_the_removal_target_is_met():
    cfg = f.FitnessConfig(target_removal=4)
    assert f.role(card("x", tags=("_removal_",)), removal(4), PINNED, cfg) == 0.0


def test_role_pays_a_creature_nothing_at_all():
    """ADR 0018: being a body earns nothing, however bare the pool.

    This is the deletion's whole content, so it is worth a test of its own
    rather than only an absence. A creature-only card scores zero against an
    empty pool at full commitment -- the most favourable case the old
    creature branch had, where it used to pay its full 0.40pp.
    """
    dude = card("x", tags=("creature",))
    assert f.role(dude, [], PINNED, f.FitnessConfig()) == 0.0
    assert f.role(dude, creatures(1), PINNED, f.FitnessConfig()) == 0.0


def test_role_still_pays_a_creature_that_is_also_removal():
    """What was retired is the reward for being a body, not for being removal.

    A removal creature is scored exactly like any other removal spell: the
    `creature` tag neither adds to it nor takes anything away.
    """
    cfg = f.FitnessConfig(target_removal=4)
    both = f.role(card("x", tags=("_removal_", "creature")), [], PINNED, cfg)
    spell = f.role(card("y", tags=("_removal_",)), [], PINNED, cfg)
    assert both == pytest.approx(0.5)
    assert both == pytest.approx(spell)


def test_role_is_a_fraction_at_p1p1_and_untagged_cards_earn_nothing():
    """The fitted ramp starts at 0, so P1P1 pays 1/14 rather than nothing."""
    cfg = f.FitnessConfig(target_removal=4)
    assert f.role(card("x", tags=("_removal_",)), [], P1P1, cfg) == pytest.approx(
        0.5 / 14
    )
    assert f.role(card("x", tags=()), [], PINNED, cfg) == 0.0


# --------------------------------------------------------------------------
# ADR 0018 -- openness is retired; there is nothing here to test
# --------------------------------------------------------------------------
# This is where the openness tests were: the rate curve, the pack-1 gate,
# the one-sided lateness clamp and the replacement-level gate. ADR 0018
# retired the term, so `openness`, `openness_rate` and `pack_weight` no
# longer exist and neither do their tests.
#
# The deletion is a backtest result, not a simplification. Over 132,246 fit
# picks the fit wanted `openness_best_rate = 0.0`, which makes the whole
# term inert; on the three reference drafts it was non-zero on 4, 9 and 5
# cards out of ~295 each, with a largest value of 0.76pp against a
# `solid_gap` of 2.0, and it never once moved a verdict. See ADR 0018 for
# the full case and `git log -- tests/test_fitness.py` for the tests.

# --------------------------------------------------------------------------
# ADR 0006 -- synergy: tag pairs against the pool
# --------------------------------------------------------------------------
# synergy_weight 1.0pp per coefficient unit (placeholder), synergy_cap 5pp.


def edge(enabler: str, payoff: str, coefficient: float, decay: float = 1.0) -> dict:
    """One authored tag_pairs row.

    `decay` defaults to 1.0 here -- no decay at all -- so that the counting
    tests below stay about counting. The schema's own default is 0.5.
    """
    return {
        "enabler": enabler,
        "payoff": payoff,
        "coefficient": coefficient,
        "decay": decay,
    }


SAC = edge("creature_sac_outlet", "dies_trigger", 0.5)
FODDER = edge("disposable_creature", "creature_sac_outlet", 0.5)
CFG = f.FitnessConfig(synergy_weight=1.0, synergy_cap=5.0)


def test_synergy_counts_copies_of_the_complementary_tag_in_the_pool():
    """A payoff with two copies of the same outlet already taken: 0.5 x 2, and the firing says why."""
    outlet = card("outlet", tags=("creature_sac_outlet",))
    result = f.synergy(card("x", tags=("dies_trigger",)), [outlet, outlet], [SAC], CFG)
    assert result.total == pytest.approx(1.0)
    assert result.top_firings == [
        f.SynergyFiring(
            tag_on_card="dies_trigger",
            complementary_tag="creature_sac_outlet",
            pool_count=2,
            effective_count=2.0,
            coefficient=0.5,
            pp=1.0,
            contributing_oracle_ids=("outlet", "outlet"),
        )
    ]


def test_a_firing_names_the_pool_cards_that_fired_it():
    """BoosterTutor #22: the brief should name them, not leave the LLM to guess."""
    outlets = [
        card("axe", tags=("creature_sac_outlet",)),
        card("altar", tags=("creature_sac_outlet",)),
    ]
    untagged = card("bear", tags=("creature",))
    result = f.synergy(
        card("x", tags=("dies_trigger",)),
        [outlets[0], untagged, outlets[1]],
        [SAC],
        CFG,
    )
    [firing] = result.top_firings
    assert firing.contributing_oracle_ids == (
        "axe",
        "altar",
    )  # pool order, the untagged card absent
    assert firing.pool_count == len(firing.contributing_oracle_ids)


def test_the_contributors_keep_duplicates_so_the_count_always_matches():
    """Copies are real copies: two of the same outlet are two contributors."""
    outlet = card("outlet", tags=("creature_sac_outlet",))
    for copies in range(1, 5):
        [firing] = f.synergy(
            card("x", tags=("dies_trigger",)), [outlet] * copies, [SAC], CFG
        ).top_firings
        assert firing.contributing_oracle_ids == ("outlet",) * copies
        assert firing.pool_count == copies


def test_the_contributors_are_not_individually_weighted():
    """The decay prices the Nth *copy*, never the Nth *card*.

    A flat list is the deliberate choice: distributing the geometric series
    across these ids by pick order would invent a ranking the arithmetic
    does not express, and pick order is not importance. The honest
    aggregate is `effective_count` and `pp`, which already say that a sixth
    copy adds almost nothing.
    """
    outlet = card("outlet", tags=("creature_sac_outlet",))
    decaying = {**SAC, "decay": 0.5}
    [firing] = f.synergy(
        card("x", tags=("dies_trigger",)), [outlet] * 6, [decaying], CFG
    ).top_firings
    assert (
        firing.contributing_oracle_ids == ("outlet",) * 6
    )  # all six, undifferentiated
    assert firing.effective_count == pytest.approx(
        1.96875, abs=1e-5
    )  # worth about two of them
    assert isinstance(firing.contributing_oracle_ids, tuple)
    assert all(isinstance(oid, str) for oid in firing.contributing_oracle_ids)


def test_synergy_reads_the_same_edge_from_the_enabler_end():
    payoff = card("payoff", tags=("dies_trigger",))
    result = f.synergy(card("x", tags=("creature_sac_outlet",)), [payoff], [SAC], CFG)
    assert result.total == pytest.approx(0.5)
    assert result.top_firings[0].complementary_tag == "dies_trigger"


def test_synergy_never_walks_two_edges():
    """Fodder in the pool does nothing for a dies_trigger card: only the outlet edge is authored."""
    fodder = card("fodder", tags=("disposable_creature",))
    result = f.synergy(
        card("x", tags=("dies_trigger",)), [fodder, fodder], [SAC, FODDER], CFG
    )
    assert result.total == 0.0 and result.top_firings == []


def test_synergy_reads_one_edge_once_not_as_an_imputed_pair():
    """One authored edge with one complementary card is one firing, never doubled by a reverse read."""
    outlet = card("outlet", tags=("creature_sac_outlet",))
    result = f.synergy(card("x", tags=("dies_trigger",)), [outlet], [SAC], CFG)
    assert result.total == pytest.approx(0.5) and len(result.top_firings) == 1


# ADR 0009: each further copy of the complementary tag is worth `decay` times
# the one before it, so n_eff is the geometric series 1 + d + d^2 + ...


@pytest.mark.parametrize(
    "n, expected", [(0, 0.0), (1, 1.0), (2, 1.5), (3, 1.75), (4, 1.875)]
)
def test_effective_count_at_the_default_decay_converges_on_two(n, expected):
    assert f.effective_count(n, 0.5) == pytest.approx(expected)


@pytest.mark.parametrize("n", [0, 1, 2, 5, 20])
def test_a_decay_of_one_is_linear(n):
    """Every copy worth the same: n_eff = n, the old uncapped behavior."""
    assert f.effective_count(n, 1.0) == float(n)


@pytest.mark.parametrize("n, expected", [(0, 0.0), (1, 1.0), (2, 1.0), (9, 1.0)])
def test_a_decay_of_zero_pays_only_the_first_copy(n, expected):
    assert f.effective_count(n, 0.0) == pytest.approx(expected)


def test_decay_shapes_a_real_firing_and_is_reported_in_the_decomposition():
    """Three sac outlets in the pool, coefficient 0.5, decay 0.5: 0.5 x 1.75."""
    outlet = card("outlet", tags=("creature_sac_outlet",))
    decaying = edge("creature_sac_outlet", "dies_trigger", 0.5, decay=0.5)
    result = f.synergy(card("x", tags=("dies_trigger",)), [outlet] * 3, [decaying], CFG)
    assert result.total == pytest.approx(0.875)
    firing = result.top_firings[0]
    assert firing.pool_count == 3 and firing.effective_count == pytest.approx(1.75)


def test_synergy_self_payoff_is_the_diagonal_and_the_total_is_capped():
    """Two copies of Seven Dwarves already held, coefficient 4: raw 8pp, held to the 5pp ceiling."""
    dwarves = card("dwarves", tags=("seven_dwarves",))
    result = f.synergy(
        dwarves, [dwarves, dwarves], [edge("seven_dwarves", "seven_dwarves", 4.0)], CFG
    )
    assert result.total == pytest.approx(5.0)
    assert result.top_firings[0].pool_count == 2


def test_synergy_surfaces_only_the_top_two_firings_above_the_floor():
    edges = [
        edge("a", "x", 1.0),
        edge("b", "x", 0.5),
        edge("c", "x", 0.3),
        edge("d", "x", 0.05),
    ]
    pool = [card(t, tags=(t,)) for t in "abcd"]
    result = f.synergy(card("x", tags=("x",)), pool, edges, CFG)
    assert result.total == pytest.approx(1.85)  # every firing counts toward the total
    assert [fr.complementary_tag for fr in result.top_firings] == ["a", "b"]

    tiny = f.synergy(card("x", tags=("x",)), [card("d", tags=("d",))], edges, CFG)
    assert tiny.total == pytest.approx(0.05) and tiny.top_firings == []


def test_synergy_is_nothing_for_an_untagged_card_or_an_empty_pool():
    assert (
        f.synergy(
            card("x"), [card("outlet", tags=("creature_sac_outlet",))], [SAC], CFG
        ).total
        == 0.0
    )
    assert f.synergy(card("x", tags=("dies_trigger",)), [], [SAC], CFG).total == 0.0


# --------------------------------------------------------------------------
# ADR 0003 s1.6 -- score_pack: the decomposition is the output
# --------------------------------------------------------------------------


def parts(cf: f.CardFitness) -> float:
    """The four conditioning terms plus base. No `openness` since ADR 0018."""
    return cf.base_unconditioned + cf.color_fit + cf.curve + cf.role + cf.synergy


def test_score_pack_at_p1p1_is_the_raw_win_rate_plus_a_fourteenth_of_the_shape_terms():
    """With ADR 0018's ramp starting at 0, P1P1 is no longer purely card quality.

    An empty pool means no tax and no synergy, but curve sees a hole at
    every mana value, so each card collects 1/14 of `curve_weight` --
    0.018pp. The point of the test is that P1P1 is still card quality to
    within a rounding error, and that the parts still sum to the total.
    """
    st = f.Stats(56.0, overall={"a": (58.0, 5000), "b": (55.0, 20000)})
    pack = [card("a", tags=("_removal_", "creature")), card("b")]
    scored = f.score_pack(
        pack, pool=[], t=1, pack_no=1, stats=st, edges=[], cfg=f.FitnessConfig()
    )
    a, b = scored
    assert (a.oracle_id, a.base_unconditioned, a.n_games) == ("a", 58.0, 5000)
    assert a.color_fit == a.synergy == 0.0
    cfg = f.FitnessConfig()
    assert a.curve == pytest.approx(cfg.curve_weight / 14)
    assert a.role == pytest.approx(cfg.removal_weight / 14)  # removal, empty pool
    assert b.role == 0.0  # untagged
    assert a.total == pytest.approx(parts(a)) and b.total == pytest.approx(parts(b))
    assert a.total == pytest.approx(58.0, abs=0.06)
    assert a.insufficient_data is False


def test_score_pack_total_is_the_sum_of_its_parts_with_every_term_live():
    outlet = card("outlet", colors="B", tags=("creature_sac_outlet",))
    pool = heavy_br_pool(6) + [outlet]
    st = heavy_br_stats(outlet=(57.0, 5000), x=(60.0, 5000), u=(62.0, 5000))
    # `_removal_` with the underscores, so the role term actually fires: the
    # bare "removal" string this used to pass is not the authored tag, and
    # before ADR 0018 the assertion below passed off the creature branch.
    pack = [
        card("x", colors="R", cmc=5.0, tags=("dies_trigger", "_removal_", "creature")),
        card("u", colors="U", cmc=5.0, tags=("creature",)),
    ]
    scored = f.score_pack(
        pack, pool, t=9, pack_no=1, stats=st, edges=[SAC], cfg=f.FitnessConfig()
    )
    for cf in scored:
        assert cf.total == pytest.approx(parts(cf))
    x, u = scored
    # Derived from the config rather than hardcoded, so tuning the weight does
    # not break a test that is about the decomposition summing correctly.
    one_outlet = f.FitnessConfig().synergy_weight * SAC["coefficient"]
    assert x.synergy == pytest.approx(one_outlet)
    assert x.top_firings[0].complementary_tag == "creature_sac_outlet"
    assert x.role > 0 and x.curve > 0
    assert u.role == 0.0  # a creature with no removal tag earns no role (ADR 0018)
    # Six BR gold cards and one mono-black: the archetype is BR and blue has
    # no presence at all, so the blue card pays one whole unit -- scaled by
    # the ramp, which is at 9/14 on pick 9 under the fitted constants.
    assert x.color_fit == 0.0
    assert u.color_fit == pytest.approx(-TAX * 9 / 14)


def test_score_pack_with_a_collapsed_pool_charges_the_whole_tax():
    st = heavy_br_stats(u=(59.0, 5000))
    [u] = f.score_pack(
        [card("u", colors="U", cmc=3.0)],
        heavy_br_pool(),
        t=PINNED,
        pack_no=1,
        stats=st,
        edges=[],
        cfg=f.FitnessConfig(),
    )
    assert u.color_fit == pytest.approx(-TAX, abs=1e-6)


def test_score_pack_flags_thin_data_but_still_scores_the_card():
    st = f.Stats(56.0, overall={"a": (58.0, 300)})
    [a] = f.score_pack(
        [card("a")], [], t=1, pack_no=1, stats=st, edges=[], cfg=f.FitnessConfig()
    )
    assert a.insufficient_data is True and a.n_games == 300
    # Still essentially the raw win rate: the only live term at P1P1 against
    # an empty pool is 1/14 of `curve_weight`, which is 0.018pp.
    assert a.total == pytest.approx(58.0, abs=0.02)


# --------------------------------------------------------------------------
# ADR 0005 -- fitness classes, verdicts, relevant picks
# --------------------------------------------------------------------------
# questionable_gap X = 3.0 (placeholder). Format average 56, replacement 53.
# BIG_FIX_#1: `solid` also needs fitness >= format average; `indifferent` is
# vetoed by any solid card or any on-color card >= replacement.


def cf(
    oracle_id: str, total: float, *, games: int = 20000, wr: float | None = None
) -> f.CardFitness:
    """A scored card for classing tests. `wr` is the raw GIH WR when it differs from the total."""
    wr = total if wr is None else wr
    return f.CardFitness(
        oracle_id=oracle_id,
        total=total,
        base_unconditioned=wr,
        color_fit=total - wr,
        curve=0.0,
        role=0.0,
        synergy=0.0,
        n_games=games,
        top_firings=[],
        insufficient_data=games < 1000,
    )


ST = stats(format_avg=56.0)


# --------------------------------------------------------------------------
# ADR 0012 s4 -- one archetype definition, shared with the role term
# --------------------------------------------------------------------------
# `on_color_pool` reads the same leading pair the tax does. Under the rule
# this replaced, a momentary tie for second place collapsed the archetype to
# None and counted the whole pool -- off-color half included -- toward the
# creature and removal targets.


def test_role_counts_only_on_color_pool_cards_once_an_archetype_is_predicted():
    """A BR pool with two BR removal spells and one blue one: blue does not count.

    Re-expressed through removal when ADR 0018 retired the creature branch;
    the on-color rule itself is unchanged and still worth testing.
    """
    cfg = f.FitnessConfig(target_removal=4)
    pool = (
        [card(f"br{i}", colors="BR") for i in range(10)]
        + [
            card("k1", colors="BR", tags=("_removal_",)),
            card("k2", colors="BR", tags=("_removal_",)),
        ]
        + [card("u", colors="U", tags=("_removal_",))]
    )
    assert f.predicted_archetype(pool) == "BR"
    # Two on-color removal spells, so two short -> the branch pays in full.
    assert f.role(
        card("x", colors="R", tags=("_removal_",)), pool, PINNED, cfg
    ) == pytest.approx(0.5)
    # A colorless removal spell is always on color: three now, one short -> half.
    pool.append(card("rock", colors="", tags=("_removal_",)))
    assert f.role(
        card("x", colors="R", tags=("_removal_",)), pool, PINNED, cfg
    ) == pytest.approx(0.25)


def test_role_counts_only_the_leading_pairs_cards_even_in_a_scattered_pool():
    """One removal spell each in U, G and W: WU leads on votes, so only two count.

    The rule this replaced saw a three-way tie, gave up, and counted all
    three -- crediting the pool for removal it could not cast.
    """
    cfg = f.FitnessConfig(target_removal=4)
    pool = [
        card("u", colors="U", tags=("_removal_",)),
        card("g", colors="G", tags=("_removal_",)),
        card("w", colors="W", tags=("_removal_",)),
    ]
    assert f.predicted_archetype(pool) == "WU"
    # Two on-color removal spells, two short -> the branch pays in full.
    assert f.role(
        card("x", colors="W", tags=("_removal_",)), pool, PINNED, cfg
    ) == pytest.approx(0.5)


def test_role_counts_copies_of_the_same_card():
    cfg = f.FitnessConfig(target_removal=4)
    same = card("kill", colors="R", tags=("_removal_",))
    assert (
        f.role(
            card("x", colors="R", tags=("_removal_",)),
            [same, same, same, same],
            PINNED,
            cfg,
        )
        == 0.0
    )


# --------------------------------------------------------------------------
# BIG_FIX_#1 round 2
# --------------------------------------------------------------------------


def test_a_hybrid_card_is_taxed_by_its_better_represented_color():
    """Either color alone pays it, so the better-represented option decides."""
    pool = pool_of(*(["U"] * 3 + ["B"] * 5 + ["R"] * 5))
    cfg = f.FitnessConfig()
    wu_hybrid = dict(card("h", colors="WU"), color_options=["W", "U"])
    # Blue is in the pool and white is not, so the hybrid is taxed as blue.
    assert f.color_fit(wu_hybrid, pool, PINNED, cfg) == pytest.approx(
        f.color_fit(card("u", colors="U"), pool, PINNED, cfg)
    )
    assert f.color_fit(wu_hybrid, pool, PINNED, cfg) > f.color_fit(
        card("w", colors="W"), pool, PINNED, cfg
    )


# --------------------------------------------------------------------------
# BIG_FIX_#1 round 3 -- hybrid cards count as dual-monocolored
# --------------------------------------------------------------------------
# A card's `color_options` are the alternative color sets that can pay it.
# Scryfall marks a {B/R} card as gold ("BR"); for playability it is a black
# card OR a red card. Pool color counts still use Scryfall's colors, so a
# hybrid card votes for both of its colors, like a gold card.


@pytest.mark.parametrize(
    "mana_cost, colors, expected",
    [
        ("{2}{B/R}", "BR", ["B", "R"]),  # pure hybrid: either color alone
        ("{1}{B/R}{B/R}", "BR", ["B", "R"]),
        ("{1}{B}{B/R}", "BR", ["B"]),  # fixed B already pays the hybrid pip
        ("{2}{W/U}{W/U}", "WU", ["U", "W"]),  # sorted WUBRG spelling, sorted list
        ("{B}{R}", "BR", ["BR"]),  # true gold: both needed
        ("{2}", "", [""]),  # colorless
        ("{2/W}", "W", [""]),  # two-hybrid: payable generically
        ("{B/P}", "B", ["B"]),  # Phyrexian: still a black pip
        ("{4}{G} // {1}{G}", "G", ["G"]),  # adventure: the front face
        ("{2} // {3}{U}", "", [""]),  # colorless front, blue adventure: colorless card
        (None, "WR", ["WR"]),  # no mana cost known: fall back to the colors
    ],
)
def test_color_options_from_a_mana_cost(mana_cost, colors, expected):
    assert f.color_options(mana_cost, colors) == expected


def hybrid(oracle_id: str, colors: str) -> dict:
    """A {X/Y} hybrid card: playable as either color."""
    return dict(card(oracle_id, colors=colors), color_options=[c for c in colors])


def test_hybrid_card_is_playable_in_any_pair_holding_either_color():
    br = hybrid("h", "BR")
    assert (
        f.playable_in(br, "UB") and f.playable_in(br, "RG") and f.playable_in(br, "BR")
    )
    assert not f.playable_in(br, "WU")
    assert (
        f.playable_in(card("gold", colors="BR"), "UB") is False
    )  # a true gold card is not


def test_hybrid_card_is_untaxed_beside_a_pool_in_either_color():
    ub_pool = pool_of(*(["U"] * 5 + ["B"] * 5))
    cfg = f.FitnessConfig()
    assert f.color_fit(hybrid("h", "BR"), ub_pool, PINNED, cfg) == pytest.approx(0.0)
    assert f.color_fit(hybrid("h", "WG"), ub_pool, PINNED, cfg) < 0.0


def test_hybrid_card_counts_toward_both_of_its_colors_pairs():
    assert f.predicted_archetype([hybrid("h", "BR"), card("r", colors="R")]) == "BR"


# --------------------------------------------------------------------------
# ADR 0012 -- the tax prices commitment, not card quality
# --------------------------------------------------------------------------
# The old term capped the penalty at `overall - replacement`, so every good
# off-color card collapsed to exactly replacement level while a weak one
# lost a flat minimum. Colors alone decide the tax now.


def test_a_weak_card_pays_the_same_tax_as_a_strong_one():
    cfg = f.FitnessConfig()
    bomb, filler = card("a", colors="U"), card("b", colors="U")
    assert f.color_fit(bomb, heavy_br_pool(), PINNED, cfg) == pytest.approx(
        f.color_fit(filler, heavy_br_pool(), PINNED, cfg)
    )


def test_classes_are_the_gap_to_the_packs_best():
    """solid within 2.0pp, questionable within 4.0pp, mistake beyond. Boundaries inclusive."""
    scored = [cf("best", 60.0), cf("edge", 58.0), cf("mid", 56.0), cf("bad", 55.9)]
    assert f.classify_pack(scored, f.FitnessConfig()) == {
        "best": "solid",
        "edge": "solid",
        "mid": "questionable",
        "bad": "mistake",
    }


def test_a_weak_pack_still_has_a_solid_best_card():
    """No absolute floor: taking the best card in a bad pack costs no equity."""
    assert (
        f.classify_pack([cf("best", 48.0), cf("worse", 43.0)], f.FitnessConfig())[
            "best"
        ]
        == "solid"
    )


def test_thin_data_does_not_widen_any_band():
    cfg = f.FitnessConfig()
    thin = f.classify_pack(
        [cf("best", 60.0, games=200), cf("bad", 55.0, games=200)], cfg
    )
    deep = f.classify_pack(
        [cf("best", 60.0, games=50000), cf("bad", 55.0, games=50000)], cfg
    )
    assert thin == deep == {"best": "solid", "bad": "mistake"}


def test_verdict_is_the_class_of_the_card_taken():
    scored = [cf("best", 60.0), cf("near", 58.5), cf("mid", 57.0)]
    cfg = f.FitnessConfig()
    assert f.verdict(scored, "near", cfg) == "solid"
    assert f.verdict(scored, "mid", cfg) == "questionable"


def test_a_pack_whose_cards_are_all_solid_is_indifferent():
    """Nothing to choose between: every card is within the solid gap of the best."""
    assert (
        f.verdict([cf("a", 60.0), cf("b", 58.0)], "b", f.FitnessConfig())
        == "indifferent"
    )


def test_two_equal_bombs_are_indifferent():
    """Reverses BIG_FIX_#1: power level does not matter, only the spread."""
    assert (
        f.verdict([cf("a", 64.0), cf("b", 63.5)], "b", f.FitnessConfig())
        == "indifferent"
    )


def test_one_card_outside_the_solid_gap_makes_the_whole_pack_a_real_pick():
    scored = [cf("a", 60.0), cf("b", 58.0), cf("c", 57.4)]
    assert f.verdict(scored, "b", f.FitnessConfig()) == "solid"


def test_a_single_card_pack_is_indifferent():
    cfg = f.FitnessConfig()
    assert f.verdict([cf("only", 40.0)], "only", cfg, pack_size=1) == "indifferent"
    assert (
        f.verdict([], "swamp", cfg, pack_size=1) == "indifferent"
    )  # a lone basic land


def test_taking_an_unscored_card_is_a_mistake_even_in_an_otherwise_flat_pack():
    """One playable plus a basic land: the spread is zero, but taking the basic is not free."""
    cfg = f.FitnessConfig()
    assert f.verdict([cf("bear", 55.0)], "bear", cfg, pack_size=2) == "indifferent"
    assert f.verdict([cf("bear", 55.0)], "swamp", cfg, pack_size=2) == "mistake"


def test_only_mistakes_earn_a_note():
    assert f.is_relevant("mistake") is True
    assert [f.is_relevant(v) for v in ("solid", "questionable", "indifferent")] == [
        False,
        False,
        False,
    ]


def test_lands_do_not_count_toward_the_curve():
    """A land is not a spell: it fills no curve slot, and has no curve of its own."""
    cfg = f.FitnessConfig()
    lands = [card(f"l{i}", cmc=0.0, tags=("land",)) for i in range(3)]
    # mv_bucket clamps 0 up to 1, so without the exclusion these would read as
    # three one-drops and make the target of two look met.
    assert f.curve(card("x", cmc=1.0), lands, PINNED, cfg) == pytest.approx(0.25)
    assert f.curve(card("x", cmc=1.0), [], PINNED, cfg) == pytest.approx(0.25)
    # And scoring a land gives no curve either way.
    assert f.curve(card("x", cmc=0.0, tags=("land",)), [], PINNED, cfg) == 0.0


# --------------------------------------------------------------------------
# ADR 0017 -- synergy measures a margin, not a level
# --------------------------------------------------------------------------
# A card's GIH WR already prices its typical synergy: cards on an authored
# edge average 2.42pp more than cards that are not. Rewarding the level paid
# twice, and the full-dump backtest drove `synergy_weight` to zero. Centred
# per card, the same term wanted 0.75 and improved both the held-out pick
# agreement and the outcome correlation.


def base_key(oracle_id, pack_no, edge, tag_on_card):
    return (oracle_id, pack_no, edge["enabler"], edge["payoff"], tag_on_card)


def test_a_typical_pool_earns_nothing():
    """The whole point: being merely average is already in the card's win rate."""
    payoff = card("x", tags=("dies_trigger",))
    outlet = card("o", tags=("creature_sac_outlet",))
    pool = [outlet, outlet]
    n_eff = f.effective_count(2, SAC["decay"])
    baseline = {base_key("x", 1, SAC, "dies_trigger"): n_eff}
    result = f.synergy(payoff, pool, [SAC], CFG, pack_no=1, baseline=baseline)
    assert result.total == pytest.approx(0.0)


def test_an_unusually_rich_pool_earns_a_bonus_and_a_poor_one_pays():
    cfg = f.FitnessConfig(synergy_weight=1.0, synergy_cap=5.0)
    payoff = card("x", tags=("dies_trigger",))
    outlet = card("o", tags=("creature_sac_outlet",))
    usual = f.effective_count(2, SAC["decay"])
    baseline = {base_key("x", 1, SAC, "dies_trigger"): usual}
    rich = f.synergy(
        payoff, [outlet] * 5, [SAC], cfg, pack_no=1, baseline=baseline
    ).total
    poor = f.synergy(payoff, [], [SAC], cfg, pack_no=1, baseline=baseline).total
    assert rich > 0.0
    assert poor == pytest.approx(-SAC["coefficient"] * usual)
    assert poor < 0.0  # signed, not clamped: a missing complement is real news


def test_an_edge_that_never_fires_for_this_card_contributes_nothing():
    """No firing and no expectation means no contribution, not a zero firing."""
    payoff = card("x", tags=("dies_trigger",))
    result = f.synergy(payoff, [], [SAC], CFG, pack_no=1, baseline={})
    assert result.total == pytest.approx(0.0)
    assert result.top_firings == []


def test_the_baseline_is_keyed_by_pack_because_pools_grow():
    payoff = card("x", tags=("dies_trigger",))
    outlet = card("o", tags=("creature_sac_outlet",))
    baseline = {
        base_key("x", 1, SAC, "dies_trigger"): 0.5,  # early: few complements expected
        base_key("x", 3, SAC, "dies_trigger"): 3.0,  # late: many
    }
    early = f.synergy(
        payoff, [outlet] * 2, [SAC], CFG, pack_no=1, baseline=baseline
    ).total
    late = f.synergy(
        payoff, [outlet] * 2, [SAC], CFG, pack_no=3, baseline=baseline
    ).total
    assert early > 0 > late  # the same pool is rich in pack 1 and poor in pack 3


def test_a_firing_reports_the_expectation_it_was_measured_against():
    payoff = card("x", tags=("dies_trigger",))
    outlet = card("o", tags=("creature_sac_outlet",))
    baseline = {base_key("x", 2, SAC, "dies_trigger"): 1.25}
    [firing] = f.synergy(
        payoff, [outlet] * 3, [SAC], CFG, pack_no=2, baseline=baseline
    ).top_firings
    assert firing.expected_count == pytest.approx(1.25)
    assert firing.pool_count == 3
    assert firing.pp == pytest.approx(
        SAC["coefficient"] * (firing.effective_count - 1.25)
    )


def test_an_empty_baseline_leaves_the_absolute_behaviour_untouched():
    """The safety property: ADR 0006's form is what you get without a baseline."""
    payoff = card("x", tags=("dies_trigger",))
    outlet = card("o", tags=("creature_sac_outlet",))
    for copies in range(4):
        pool = [outlet] * copies
        assert f.synergy(
            payoff, pool, [SAC], CFG, pack_no=2, baseline=None
        ).total == pytest.approx(f.synergy(payoff, pool, [SAC], CFG).total)
