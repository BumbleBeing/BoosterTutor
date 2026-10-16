"""The Submitted Deck's metrics (ADR 0026 s1, the mana and land metrics of ADR 0028)."""

import uuid
from typing import Any

import pytest

from boostertutor.analysis import fitness as fx
from boostertutor.analysis.deck import deck_metrics
from boostertutor.analysis.draft import FormatInputs, fitness_card
from boostertutor.analysis.mana import LandTarget, ManaSource
from boostertutor.schemas.deck import Deck

FORMAT_AVG = 55.0

# A format with a 17 band: 16 lands below 2.2 average mana value, 18 from 3.2.
THREE_BANDS = LandTarget(low=16, middle=17, high=18, low_below_mv=2.2, high_from_mv=3.2)


class Set:
    """A tiny made-up set: cards by name, with their win rates."""

    def __init__(self) -> None:
        self.cards: dict[uuid.UUID, dict[str, Any]] = {}
        self.ids: dict[str, uuid.UUID] = {}
        self.overall: dict[uuid.UUID, tuple[float, int]] = {}
        self.mana_sources: dict[uuid.UUID, ManaSource] = {}

    def card(
        self,
        name: str,
        mana_cost: str | None = "{1}{W}",
        *,
        type_line: str = "Creature — Human",
        gih_wr: float = FORMAT_AVG,
        tags: list[str] | None = None,
        color_identity: str | None = None,
    ) -> uuid.UUID:
        oid = uuid.uuid5(uuid.NAMESPACE_URL, name)
        pips = fx.PIP_RE.findall(mana_cost or "")
        colors = "".join(c for c in "WUBRG" if any(c in p for p in pips))
        cmc = sum(int(p) if p.isdigit() else 1 for p in pips)
        self.cards[oid] = fitness_card(
            oid,
            type_line=type_line,
            mana_cost=mana_cost,
            cmc=float(cmc),
            colors=colors,
            color_identity=colors if color_identity is None else color_identity,
            tags=tags or [],
        )
        self.ids[name] = oid
        self.overall[oid] = (gih_wr, 5000)
        return oid

    def inputs(
        self,
        edges: list[dict[str, Any]] | None = None,
        land_target: LandTarget = THREE_BANDS,
    ) -> FormatInputs:
        return FormatInputs(
            set_code="tst",
            event_type="PremierDraft",
            stats_snapshot="2026-10-01",
            cards=self.cards,
            stats=fx.Stats(format_avg_wr=FORMAT_AVG, overall=self.overall),
            edges=edges or [],
            mana_sources=self.mana_sources,
            land_target=land_target,
            cfg=fx.FitnessConfig(target_curve={1: 2, 2: 8, 3: 7, 4: 4, 5: 2, 6: 1}),
        )


def white_deck(s: Set, spells: list[uuid.UUID], plains: int = 17) -> Deck:
    """`spells`, padded to 40 with vanilla two-drops and Plains."""
    filler = 40 - plains - len(spells)
    bears = [s.card(f"Bear {i}", "{1}{W}") for i in range(filler)]
    return Deck(main=spells + bears, basics={"W": plains}, sideboard=[])


def test_card_quality_is_the_mean_nonland_win_rate_against_the_format_average() -> None:
    s = Set()
    good = s.card("Good", gih_wr=61.0)  # 23 spells: one at +6, the rest at 0
    metrics = deck_metrics(white_deck(s, [good]), s.inputs())

    assert metrics.card_quality == pytest.approx(6.0 / 23)


def test_curve_counts_nonland_cards_by_mana_value_and_the_distance_from_target() -> (
    None
):
    s = Set()
    spells = [s.card(f"Three {i}", "{2}{W}") for i in range(7)]
    spells += [s.card("Seven", "{6}{W}")]  # 7+ counts with the sixes
    metrics = deck_metrics(white_deck(s, spells), s.inputs())

    # 15 two-drops, 7 three-drops, 1 six-drop against 2/8/7/4/2/1.
    assert metrics.curve == {1: 0, 2: 15, 3: 7, 4: 0, 5: 0, 6: 1}
    assert metrics.curve_distance == 2 + 7 + 0 + 4 + 2 + 0


def test_synergy_sums_each_cards_firings_against_the_rest_of_the_deck() -> None:
    s = Set()
    outlet = s.card("Outlet", tags=["sac_outlet"])
    fodder = [s.card(f"Fodder {i}", tags=["fodder"]) for i in range(2)]
    edges = [
        {"enabler": "fodder", "payoff": "sac_outlet", "coefficient": 1.0, "decay": 0.5}
    ]
    metrics = deck_metrics(white_deck(s, [outlet, *fodder]), s.inputs(edges))

    # The outlet finds two fodder (n_eff 1.5); each fodder finds one outlet.
    # synergy_weight is 0.75 pp per coefficient unit.
    assert metrics.synergy == pytest.approx(0.75 * (1.5 + 1 + 1))
    top = metrics.synergy_firings[0]
    assert (top.oracle_id, top.complementary_tag, top.count) == (outlet, "fodder", 2)
    assert top.contributing == fodder


def test_creatures_and_removal_are_counted_in_the_main_deck() -> None:
    s = Set()
    removal = [
        s.card(f"Bolt {i}", "{R}", type_line="Instant", tags=["_removal_"])
        for i in range(3)
    ]
    metrics = deck_metrics(white_deck(s, removal), s.inputs())

    assert (metrics.creatures, metrics.removal) == (20, 3)


def deck_of(s: Set, spells: list[uuid.UUID], basics: dict[str, int]) -> Deck:
    """`spells` and `basics`, padded to 40 with colourless two-drops."""
    filler = 40 - sum(basics.values()) - len(spells)
    golems = [
        s.card(f"Golem {i}", "{2}", type_line="Artifact Creature")
        for i in range(filler)
    ]
    return Deck(main=spells + golems, basics=basics, sideboard=[])


def test_a_spell_with_enough_sources_is_not_short() -> None:
    s = Set()
    metrics = deck_metrics(
        deck_of(s, [s.card("Knight", "{W}{W}")], {"W": 17}), s.inputs()
    )

    # CC needs 14 sources (Karsten, 40 cards); 17 Plains is more than enough.
    assert (metrics.mana_shortfall, metrics.spells_short) == (0.0, 0)
    assert metrics.mana_short_spell is None


def test_the_mana_metric_is_the_largest_shortfall_and_names_its_spell() -> None:
    s = Set()
    ogre = s.card("Ogre", "{1}{R}{R}")
    spells = [ogre, s.card("Goblin", "{R}"), s.card("Knight", "{1}{W}")]
    metrics = deck_metrics(deck_of(s, spells, {"W": 9, "R": 8}), s.inputs())

    # 1CC needs 12 red sources and C needs 9; the deck has 8.
    assert metrics.mana_shortfall == 4.0
    assert (metrics.mana_short_spell, metrics.mana_short_colors) == (ogre, "R")
    assert (metrics.mana_required, metrics.mana_available) == (12, 8.0)
    assert metrics.spells_short == 2


def test_a_gold_spell_needs_one_more_source_of_each_colour() -> None:
    s = Set()
    boros = s.card("Boros", "{W}{R}")
    metrics = deck_metrics(deck_of(s, [boros], {"W": 9, "R": 8}), s.inputs())

    # For red, {W}{R} is a 1C spell (9 sources), plus one for being gold.
    assert (metrics.mana_shortfall, metrics.mana_short_colors) == (2.0, "R")
    assert metrics.mana_required == 10


def test_a_hybrid_symbol_is_met_by_sources_of_either_colour() -> None:
    s = Set()
    hybrid = s.card("Hybrid", "{2}{W/R}")
    metrics = deck_metrics(deck_of(s, [hybrid], {"W": 4, "R": 4, "U": 9}), s.inputs())

    # 2C needs 8, and four Plains plus four Mountains are eight.
    assert metrics.mana_shortfall == 0.0


def test_a_dual_land_is_a_source_of_both_its_colours() -> None:
    s = Set()
    ogre = s.card("Ogre", "{1}{R}{R}")
    dual = s.card("Goblin-town", None, type_line="Land", color_identity="BR")
    metrics = deck_metrics(deck_of(s, [ogre, dual], {"W": 8, "R": 8}), s.inputs())

    assert metrics.mana_available == 9.0


def test_a_fixer_counts_its_weight_only_toward_spells_at_its_minimum_mana_value() -> (
    None
):
    s = Set()
    dori = s.card("Dori", "{2}{R}")
    s.mana_sources[dori] = ManaSource("treasure", "WUBRG", 0.25, 0.0, 3)
    ogre, pair = s.card("Ogre", "{1}{R}{R}"), s.card("Pair", "{R}{R}")
    metrics = deck_metrics(deck_of(s, [dori, ogre, pair], {"W": 9, "R": 8}), s.inputs())

    # The two-drop gets nothing from the Treasure: CC needs 14 of 8.
    assert (metrics.mana_shortfall, metrics.mana_short_spell) == (6.0, pair)
    # The three-drop gets a quarter: 1CC needs 12 of 8.25.
    s.cards.pop(pair)
    deck = deck_of(s, [dori, ogre], {"W": 9, "R": 8})
    assert deck_metrics(deck, s.inputs()).mana_shortfall == pytest.approx(3.75)


def test_a_basic_fetcher_fixes_only_for_basics_the_deck_runs() -> None:
    s = Set()
    hole = s.card("Hobbit Hole", None, type_line="Land", color_identity="")
    s.mana_sources[hole] = ManaSource("fetch_basic", "basics", 1.0, 1.0, 0)
    knight, merfolk = s.card("Knight", "{W}{W}"), s.card("Merfolk", "{U}{U}")
    two_colours = deck_of(s, [hole, knight, merfolk], {"W": 10, "R": 6})

    # A Plains to fetch, but no Island.
    metrics = deck_metrics(two_colours, s.inputs())
    assert (metrics.mana_short_spell, metrics.mana_available) == (merfolk, 0.0)
    assert metrics.spells_short == 2  # the Knight has 11 of 14

    # In a deck of three basic types it counts two thirds, as it forces a choice.
    three_colours = deck_of(s, [hole, knight], {"W": 10, "R": 5, "U": 1})
    assert deck_metrics(three_colours, s.inputs()).mana_available == pytest.approx(
        10 + 2 / 3
    )


def test_a_low_curve_wants_16_lands_and_being_over_costs_half() -> None:
    s = Set()
    metrics = deck_metrics(white_deck(s, []), s.inputs())  # 23 two-drops

    assert (metrics.average_mana_value, metrics.land_target) == (2.0, 16)
    assert (metrics.effective_lands, metrics.land_distance) == (17.0, 0.5)


def test_a_fixer_counts_its_land_weight_and_being_short_costs_in_full() -> None:
    s = Set()
    troop = s.card("Troop of Ponies", "{2}")
    s.mana_sources[troop] = ManaSource("ramp_spell_3", "basics", 0.5, 0.5, 5)
    spells = [troop] + [s.card(f"Three {i}", "{2}{W}") for i in range(10)]
    metrics = deck_metrics(white_deck(s, spells, plains=15), s.inputs())

    # 25 spells at an average of 2.4 want 17 lands; 15 Plains and a half.
    assert metrics.land_target == 17
    assert (metrics.effective_lands, metrics.land_distance) == (15.5, 1.5)


def test_a_high_curve_wants_18_lands() -> None:
    s = Set()
    spells = [s.card(f"Five {i}", "{4}{W}") for i in range(23)]
    metrics = deck_metrics(white_deck(s, spells), s.inputs())

    assert (metrics.land_target, metrics.land_distance) == (18, 1.0)


def test_a_format_may_have_no_17_band() -> None:
    """HOB's measured rule: 16 lands below an average of 3.0, 18 from 3.0."""
    hob = LandTarget(low=16, middle=17, high=18, low_below_mv=3.0, high_from_mv=3.0)
    s = Set()
    low = [s.card(f"Three {i}", "{2}{W}") for i in range(10)]  # averages 2.43
    high = [s.card(f"Four {i}", "{3}{W}") for i in range(23)]  # averages exactly 4.0
    even = [s.card(f"Four {i}", "{3}{W}") for i in range(8)] + low[:7]  # exactly 3.0

    assert deck_metrics(white_deck(s, low), s.inputs(land_target=hob)).land_target == 16
    assert (
        deck_metrics(white_deck(s, high), s.inputs(land_target=hob)).land_target == 18
    )
    assert (
        deck_metrics(white_deck(s, even), s.inputs(land_target=hob)).land_target == 18
    )


def test_the_notable_omission_is_the_best_playable_sideboard_card_well_above_the_weakest() -> (
    None
):
    s = Set()
    weak = s.card("Weak", gih_wr=50.0)
    deck = white_deck(s, [weak])  # everything else is at 55
    benched = s.card("Benched", "{2}{W}", gih_wr=58.0)
    better = s.card("Better", "{3}{W}", gih_wr=60.0)
    off_colour = s.card("Off colour", "{1}{B}", gih_wr=70.0)
    deck = deck.model_copy(update={"sideboard": [benched, better, off_colour]})

    omission = deck_metrics(deck, s.inputs()).notable_omission
    # 60 - 50 = 10 points, past mistake_gap (4).
    assert omission is not None
    assert (omission.oracle_id, omission.gih_wr) == (better, 60.0)
    assert (omission.instead_of, omission.instead_of_gih_wr) == (weak, 50.0)


def test_there_is_no_notable_omission_within_the_mistake_gap() -> None:
    s = Set()
    deck = white_deck(s, [s.card("Weak", gih_wr=53.0)])
    deck = deck.model_copy(update={"sideboard": [s.card("Benched", gih_wr=57.0)]})

    assert deck_metrics(deck, s.inputs()).notable_omission is None


def test_colour_sources_count_lands_and_fixers_for_the_colours_spells_use() -> None:
    from boostertutor.analysis.mana import colour_sources

    s = Set()
    white = s.card("White Knight", "{1}{W}")
    red = s.card("Red Bolt", "{R}", type_line="Instant")
    dori = s.card("Dori", "{2}", type_line="Artifact")
    s.mana_sources[dori] = ManaSource("treasure", "WUBRG", 0.5, 0.5)
    cards = [s.cards[white], s.cards[red], s.cards[dori]]
    result = colour_sources(cards, {"W": 8, "R": 7}, s.mana_sources)
    # Green and black have no pips among the spells, so they are left out.
    assert result == {"W": 8.5, "R": 7.5}
