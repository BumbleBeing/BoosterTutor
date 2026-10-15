"""The brief for one Noted Pick (ADR 0024 s5).

The brief is the contract the Pick Note's invented-statistic check runs
against, so every number in it is display text, written once, here. The
expected strings below were read off the golden analysis and the card
facts fixture by hand, not recomputed.
"""

import uuid

import pytest

from boostertutor.analysis.fitness import FitnessConfig
from boostertutor.briefing import PickBrief, noted_pick_briefs
from boostertutor.briefing import pick_brief as _pick_brief
from boostertutor.briefing.card_facts import CardFacts
from boostertutor.schemas.draft_analysis import DraftAnalysis

ORACLE = {
    "Pinecone Strike": "Pinecone Strike deals 3 damage to target creature.",
    "Dwarven Mauler": "Equip abilities you activate that target this creature",
    "Lakeshore Apothecary": "Whenever you draw your second card each turn",
    "Smaug's Fury": "Target creature gets +3/+0",
    "Stone by Sunlight": "Destroy target creature with power 4 or greater.",
}


CFG = FitnessConfig()  # the fixture's format settings are the defaults


def pick_brief(*args: object, **kwargs: int) -> PickBrief:
    return _pick_brief(*args, CFG, **kwargs)  # type: ignore[arg-type]


def text(analysis: DraftAnalysis, facts: dict[uuid.UUID, CardFacts], pick: str) -> str:
    pack, number = (int(n) for n in pick.removeprefix("P").split("p"))
    return pick_brief(analysis, facts, pack_number=pack, pick_number=number).text


def test_a_brief_says_which_pick_and_how_it_was_judged(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    brief = pick_brief(analysis, card_facts, pack_number=1, pick_number=1)
    assert (brief.pack_number, brief.pick_number, brief.kind) == (1, 1, "critical")
    assert "Pack 1, pick 1" in brief.text
    assert "Verdict: questionable" in brief.text
    assert "Card taken: Dwarven Mauler" in brief.text
    assert "Best card: Pinecone Strike" in brief.text


def test_every_number_is_display_text(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    """P1p1 from the golden: Mauler 57.229 (57.293%, 18,606 games), Strike 59.425."""
    brief = text(analysis, card_facts, "P1p1")
    assert "2.2pp" in brief  # the gap, 2.196
    assert "57.3%" in brief and "18,606 games" in brief  # Mauler's GIH WR
    assert "59.4%" in brief and "55,707 games" in brief  # Strike's
    assert "fitness 57.2" in brief and "fitness 59.4" in brief
    # Python does the comparison, so Claude never subtracts: Strike's GIH WR
    # is 59.371 - 57.293 = 2.078 higher.
    assert "GIH WR +2.1pp" in brief
    # Raw floats never leak through.
    assert "57.229" not in brief and "2.196" not in brief


def test_oracle_text_only_for_the_card_taken_and_the_best(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    brief = text(analysis, card_facts, "P1p1")
    assert ORACLE["Dwarven Mauler"] in brief
    assert ORACLE["Pinecone Strike"] in brief
    assert ORACLE["Lakeshore Apothecary"] not in brief
    # Every other card still gets its name, cost, rarity and type line.
    assert "Lakeshore Apothecary {1}{U} · common · Creature — Human Cleric" in brief


def test_a_narrow_pick_also_shows_the_next_two_cards(
    eval_analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    """P2p3 of the eval draft: Stone by Sunlight, the pack's only solid card."""
    brief = pick_brief(eval_analysis, card_facts, pack_number=2, pick_number=3)
    assert brief.kind == "narrow"
    assert "Card taken: Stone by Sunlight" in brief.text
    assert ORACLE["Stone by Sunlight"] in brief.text
    pick = next(
        p for p in eval_analysis.picks if (p.pack_number, p.pick_number) == (2, 3)
    )
    runners_up = [card_facts[c.oracle_id] for c in pick.cards[1:3]]
    for card in runners_up:
        assert f"Runner-up: {card.name}" in brief.text
        assert card.oracle_text
        for line in card.oracle_text.splitlines():
            assert line in brief.text


def test_a_brief_knows_only_the_moment_of_the_pick(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    """ADR 0024 s2: no wheels and no later picks, so a live note and a review's agree."""
    at_the_time = analysis.model_copy(
        update={"picks": analysis.picks[:12], "wheels": []}
    )
    assert text(at_the_time, card_facts, "P1p12") == text(analysis, card_facts, "P1p12")


def test_a_brief_describes_the_pool_before_the_pick(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    """P1p12: eleven cards, leaning red-green (from the golden's pool state)."""
    brief = text(analysis, card_facts, "P1p12")
    assert "Pool before this pick: 11 cards" in brief
    assert "Leading pair: RG" in brief
    assert "Creatures 3, removal 2" in brief


def test_taking_a_basic_land_is_explained_as_unscored(
    examples_analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    brief = text(examples_analysis, card_facts, "P3p10")
    assert "Card taken: Mountain" in brief
    assert "never scored" in brief


def test_only_a_noted_pick_has_a_brief(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    with pytest.raises(ValueError, match="not a Noted Pick"):
        pick_brief(analysis, card_facts, pack_number=1, pick_number=2)


def test_a_card_without_facts_is_refused(analysis: DraftAnalysis) -> None:
    with pytest.raises(LookupError):
        pick_brief(analysis, {}, pack_number=1, pick_number=1)


def test_a_draft_s_briefs_are_its_noted_picks_in_order(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    briefs = noted_pick_briefs(analysis, card_facts, CFG)
    assert [(b.pack_number, b.pick_number) for b in briefs] == [(1, 1), (1, 12), (2, 7)]
