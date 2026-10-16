"""The Draft Summary's brief (ADR 0030 s2), on the HOB golden draft.

The decks here are this file's own, built for the tests. The eval's two
fixture decks, which Jackson builds, are in `tests/fixtures/decks/`.
"""

import re
import uuid

import pytest
from conftest import load_deck_inputs

from boostertutor.analysis.deck import deck_metrics
from boostertutor.analysis.deck_rating import rate_deck
from boostertutor.briefing.card_facts import CardFacts
from boostertutor.briefing.summary import SummaryBrief, summary_brief
from boostertutor.schemas.deck import Deck, DeckError, deck_from_names, drafted_pool
from boostertutor.schemas.draft_analysis import DraftAnalysis

INPUTS, MODEL, _ = load_deck_inputs()

# A black-red deck from the golden pool: 23 spells, Goblin-town and 16 basics.
BR_SPELLS = [
    "Dwarven Mauler",
    "Pinecone Strike",
    "Pinecone Strike",
    "Tidings of War",
    "Tidings of War",
    "Smaug's Fury",
    "Óin the Brave",
    "Thorin, Mountain-king",
    "Burn, Burn, Tree and Fern",
    "Gandalf, Spark Starter",
    "Bombur, Gentle Dreamer",
    "Nori, Teller of Tales",
    "Nori, Teller of Tales",
    "Dwalin, Weaponmaster",
    "Bilbo's Deadly Slice",
    "Crude Bent Blade",
    "Crude Bent Blade",
    "Rhovanion Rampager",
    "Gollum, Silent Slinker // Meager Meal",
    "Gollum, Silent Slinker // Meager Meal",
    "Dreaded Bat-Cloud",
    "Bolg of the North",
    "Front Porch Sentries",
]
BR_DECK = [*BR_SPELLS, "Goblin-town", *["Mountain"] * 9, *["Swamp"] * 7]


def names(cards: dict[uuid.UUID, CardFacts]) -> dict[str, uuid.UUID]:
    return {facts.name: oid for oid, facts in cards.items()}


def build(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts], deck: list[str]
) -> Deck:
    return deck_from_names(drafted_pool(analysis, card_facts), deck, names(card_facts))


def brief_for(
    analysis: DraftAnalysis,
    card_facts: dict[uuid.UUID, CardFacts],
    deck_names: list[str],
    *,
    rated: bool = True,
) -> SummaryBrief:
    deck = build(analysis, card_facts, deck_names)
    metrics = deck_metrics(deck, INPUTS)
    ratings = rate_deck(metrics, MODEL if rated else None)
    return summary_brief(analysis, deck, metrics, ratings, card_facts, INPUTS)


# --------------------------------------------------------------------------
# The deck, from card names
# --------------------------------------------------------------------------


def test_the_drafted_pool_leaves_out_the_basics_taken(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    pool = drafted_pool(analysis, card_facts)
    assert len(pool) == 40  # 42 picks, less a Forest and a Swamp
    assert {card_facts[oid].name for oid in pool}.isdisjoint({"Forest", "Swamp"})


def test_a_deck_of_names_counts_basics_by_colour_and_keeps_the_rest_aside(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    deck = build(analysis, card_facts, BR_DECK)
    assert deck.basics == {"R": 9, "B": 7}
    assert len(deck.main) == 24 and len(deck.sideboard) == 16


def test_a_name_that_is_not_in_the_pool_is_refused_by_name(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    with pytest.raises(DeckError, match="Lightning Bolt"):
        build(analysis, card_facts, [*BR_DECK[:-1], "Lightning Bolt"])


# --------------------------------------------------------------------------
# The brief
# --------------------------------------------------------------------------


def test_every_pick_gets_one_line_with_its_verdict_and_gap(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    text = brief_for(analysis, card_facts, BR_DECK).text
    lines = re.findall(r"^- P\dp\d+ .*$", text, re.MULTILINE)
    assert len(lines) == 42
    assert "- P1p1 Dwarven Mauler · questionable · 2.2pp below the best" in lines
    assert "- P2p1 Thorin, Mountain-king · solid · the best card" in lines
    assert "- P2p14 Forest · indifferent · a basic land, never scored" in lines
    assert "34 solid, 3 questionable, 0 mistake, 5 indifferent" in text


def test_the_noted_picks_are_given_in_full_and_their_notes_are_not(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    text = brief_for(analysis, card_facts, BR_DECK).text
    noted = text[text.index("## The Noted Picks") : text.index("## What wheeled")]
    assert [m for m in re.findall(r"^### (P\dp\d+)", noted, re.MULTILINE)] == [
        "P1p1",
        "P1p12",
        "P2p7",
    ]
    assert noted.count("Best card: ") == 3
    assert noted.count("Largest part: ") == 3
    assert "Pick Note" not in text


def test_the_wheels_say_what_came_back_by_colour(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    text = brief_for(analysis, card_facts, BR_DECK).text
    wheels = text[text.index("## What wheeled") : text.index("## The Reviewed Deck")]
    assert wheels.count("Pack ") >= 3
    assert re.search(r"R: \d+ good card\(s\) of \d+ wheeled", wheels)
    assert "the format average of 56.3%" in wheels


def test_the_deck_is_listed_with_its_basics(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    text = brief_for(analysis, card_facts, BR_DECK).text
    deck = text[text.index("## The Reviewed Deck") : text.index("## Deck Ratings")]
    assert "Spells (23)" in deck
    assert "Lands (17): Goblin-town; Swamp ×7; Mountain ×9" in deck
    assert "- Thorin, Mountain-king {3}{R} · Legendary Creature — Dwarf Noble" in deck


def test_the_ratings_carry_the_17lands_caveat_and_a_grade_per_metric(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    text = brief_for(analysis, card_facts, BR_DECK).text
    ratings = text[text.index("## Deck Ratings") :]
    assert "relative to 17Lands players" in ratings
    assert re.search(r"Overall: grade [A-F] \(\d+(st|nd|rd|th) percentile\)", ratings)
    for label in ("Card quality", "Curve", "Synergy", "Creatures", "Removal"):
        assert re.search(rf"^- {label}: .* grade [A-F]", ratings, re.MULTILINE), label
    assert re.search(r"^- Mana: .* grade [A-F]", ratings, re.MULTILINE)
    assert re.search(r"^- Lands: .* grade [A-F]", ratings, re.MULTILINE)


def test_a_red_deck_short_of_mountains_names_its_mana_shortfall(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    starved = [*BR_SPELLS, "Goblin-town", *["Mountain"] * 3, *["Swamp"] * 13]
    text = brief_for(analysis, card_facts, starved).text
    assert re.search(r"needs \d+ red sources; the deck has \d+\.\d", text)
    assert re.search(r"\d+ spell\(s\) are short of sources", text)


def test_a_deck_with_enough_sources_says_so(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    # BR_DECK is short of black for Bilbo's Deadly Slice {1}{B}{B}; swap it
    # and the pip-heavy Gandalf for two single-pip red cards, and even out
    # the basics, so Goblin-town makes 9 sources of each colour.
    spells = [
        s
        for s in BR_SPELLS
        if s not in ("Bilbo's Deadly Slice", "Gandalf, Spark Starter")
    ]
    spells += ["Goblin-town Flunkies", "Ragged Short Spear"]
    deck = [*spells, "Goblin-town", *["Mountain"] * 8, *["Swamp"] * 8]
    text = brief_for(analysis, card_facts, deck).text
    assert "every spell has the sources it needs" in text


def test_an_unrated_format_says_not_enough_data_to_rate(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    text = brief_for(analysis, card_facts, BR_DECK, rated=False).text
    assert "not enough data to rate" in text
    assert "grade " not in text[text.index("## Deck Ratings") :]


def test_a_basic_land_is_never_a_good_card_that_wheeled(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    text = brief_for(analysis, card_facts, BR_DECK).text
    wheeled = re.findall(r"^- from pick \d+ to pick \d+: ([^·]+) ·", text, re.MULTILINE)
    assert wheeled
    assert {w.strip() for w in wheeled}.isdisjoint({"Mountain", "Swamp", "Forest"})


def test_two_copies_of_a_card_name_its_synergy_once(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    text = brief_for(analysis, card_facts, BR_DECK).text
    firings = re.findall(r"^  .*: its .* finds .*$", text, re.MULTILINE)
    assert firings
    assert len(firings) == len(set(firings))
