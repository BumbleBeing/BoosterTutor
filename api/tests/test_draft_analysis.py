"""`analyze_draft` on a real draft (development plan 3.3 and 3.5).

The draft and its inputs are the fixtures in `conftest.py`.

The golden file is the whole analysis. When the analysis changes on
purpose, regenerate it and read the diff:

    UPDATE_GOLDEN=1 uv run pytest tests/test_draft_analysis.py
"""

import json
import os
import uuid
from pathlib import Path
from typing import Any

import pytest

from boostertutor.analysis import fitness as fx
from boostertutor.analysis.draft import (
    FormatInputs,
    analyze_draft,
    fitness_card,
    is_basic_land,
)
from boostertutor.format_inputs import fitness_config
from boostertutor.models import FormatConstants
from boostertutor.parsing.names import name_key
from boostertutor.schemas import DraftLog
from boostertutor.schemas.draft_analysis import DraftAnalysis

GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "hob.d9ac6765.analysis.json"


def _json(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text())
    return data


# --------------------------------------------------------------------------
# The golden file
# --------------------------------------------------------------------------


def test_the_analysis_matches_the_golden_file(analysis: DraftAnalysis) -> None:
    produced = analysis.model_dump(mode="json")
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(produced, indent=1) + "\n")
    assert produced == _json(GOLDEN)


# --------------------------------------------------------------------------
# Properties that hold on every pick
# --------------------------------------------------------------------------


def test_every_pick_is_analysed_in_order(
    analysis: DraftAnalysis, log: DraftLog
) -> None:
    assert len(analysis.picks) == len(log.picks) == 42
    assert analysis.pack_size == 14
    assert analysis.has_taxonomy
    for i, (pa, pick) in enumerate(zip(analysis.picks, log.picks, strict=True)):
        assert (pa.pack_number, pa.pick_number, pa.picked) == (
            pick.pack_number,
            pick.pick_number,
            pick.picked,
        )
        assert pa.pool.size == i
        # One score per distinct card in the pack, best first.
        assert [c.oracle_id for c in pa.cards] != []
        assert {c.oracle_id for c in pa.cards} == set(pick.pack_cards)
        totals = [c.total for c in pa.cards if c.total is not None]
        assert totals == sorted(totals, reverse=True)


def test_each_verdict_agrees_with_the_gap(
    analysis: DraftAnalysis, inputs: FormatInputs
) -> None:
    cfg = inputs.cfg
    for pa in analysis.picks:
        taken = next(c for c in pa.cards if c.oracle_id == pa.picked)
        if not taken.scored:
            # Taking a basic land is a mistake, unless it was the only card
            # left: a pack of one is no choice at all.
            alone = len(pa.cards) == 1
            assert pa.verdict == ("indifferent" if alone else "mistake")
            assert pa.gap is None
            continue
        assert pa.gap is not None and pa.gap >= 0
        if pa.verdict == "indifferent":
            continue
        assert pa.verdict == taken.fitness_class
        expected = (
            "solid"
            if pa.gap <= cfg.solid_gap
            else "questionable"
            if pa.gap <= cfg.mistake_gap
            else "mistake"
        )
        assert pa.verdict == expected


def test_the_parts_of_every_score_add_up(analysis: DraftAnalysis) -> None:
    for pa in analysis.picks:
        for c in pa.cards:
            if c.scored:
                assert c.gih_wr is not None and c.total is not None
                parts = c.gih_wr + c.color_fit + c.curve + c.role + c.synergy
                assert parts == pytest.approx(c.total, abs=0.003)  # rounding only
                assert c.color_fit <= 0


def test_the_last_pick_of_each_pack_is_indifferent(analysis: DraftAnalysis) -> None:
    for pa in analysis.picks:
        if pa.pick_number == 14:
            assert pa.verdict == "indifferent"


def test_hob_has_three_noted_picks_and_no_narrow_ones(analysis: DraftAnalysis) -> None:
    """ADR 0024 s1: the three questionable picks earn notes, all critical.

    HOB has six packs with a single solid card, and none of them has two
    questionable ones, so the "one bomb and chaff" exclusion holds here.
    """
    noted = [(p.pack_number, p.pick_number) for p in analysis.picks if p.noted]
    assert noted == [(1, 1), (1, 12), (2, 7)]
    assert not any(p.narrow for p in analysis.picks)


def test_the_pool_ends_as_the_drafter_s_deck_colours(analysis: DraftAnalysis) -> None:
    """17Lands records this deck as BR; the pool before the last pick agrees."""
    assert analysis.picks[-1].pool.predicted_archetype == "BR"


# --------------------------------------------------------------------------
# One pick worked by hand (plan 3.5)
# --------------------------------------------------------------------------


def test_p1p1_dwarven_mauler_by_hand(
    analysis: DraftAnalysis, inputs: FormatInputs, names: dict[str, uuid.UUID]
) -> None:
    """P1p1: Dwarven Mauler, a one-mana red Dwarf, into an empty pool.

    t = 1, so the commitment lambda = (1 - 0) / 14 = 0.0714.
      color_fit: an empty pool predicts no archetype, so no tax: 0.
      curve:     no one-drops yet and the target is 2, so a hole is filled:
                 +0.25 x 0.0714 = +0.0179.
      role:      not tagged `_removal_`: 0.
      synergy:   Mauler sits on two edges, and an empty pool finds nothing
                 on either, against what Mauler usually finds at pack 1:
                   dwarf -> dwarf_payoff (coefficient 0.2): E = 0.0480
                   equipment -> equipment_payoff (0.4):     E = 0.2507
                 0.75 x (0.2 x (0 - 0.0480) + 0.4 x (0 - 0.2507))
                 = 0.75 x (-0.0096 - 0.1003) = -0.0824.
    total = GIH WR + 0.0179 - 0.0824.
    """
    mauler = names[name_key("Dwarven Mauler")]
    gih_wr, games = inputs.stats.overall[mauler]
    assert "_removal_" not in inputs.cards[mauler]["tags"]
    expected_dwarf = inputs.baseline[(mauler, 1, "dwarf", "dwarf_payoff", "dwarf")]
    expected_equipment = inputs.baseline[
        (mauler, 1, "equipment", "equipment_payoff", "equipment_payoff")
    ]
    assert (round(expected_dwarf, 4), round(expected_equipment, 4)) == (0.048, 0.2507)

    p1p1 = analysis.picks[0]
    score = next(c for c in p1p1.cards if c.oracle_id == mauler)
    assert p1p1.commitment == pytest.approx(1 / 14, abs=0.001)
    assert (score.color_fit, score.role) == (0.0, 0.0)
    assert score.curve == pytest.approx(0.0179, abs=0.001)
    assert score.synergy == pytest.approx(-0.0824, abs=0.001)
    assert score.total == pytest.approx(gih_wr + 0.0179 - 0.0824, abs=0.001)
    assert score.games == games


# --------------------------------------------------------------------------
# The pieces
# --------------------------------------------------------------------------


def test_fitness_card_derives_creature_and_land_from_the_type_line() -> None:
    oid = uuid.UUID(int=1)
    kwargs: dict[str, Any] = {
        "mana_cost": None,
        "cmc": 0.0,
        "colors": "",
        "color_identity": "BR",
        "tags": ["_removal_"],
    }
    land = fitness_card(oid, type_line="Land", **kwargs)
    assert land["tags"] == ["_removal_", "land"]
    assert land["color_options"] == ["B", "R"]  # a dual land serves either colour
    dryad = fitness_card(oid, type_line="Land Creature — Dryad", **kwargs)
    assert dryad["tags"] == ["_removal_", "creature", "land"]


def test_basic_lands_are_recognised_by_type_line() -> None:
    assert is_basic_land({"type_line": "Basic Land — Swamp"})
    assert not is_basic_land({"type_line": "Land"})


def test_a_draft_from_another_format_is_refused(
    log: DraftLog, inputs: FormatInputs
) -> None:
    other = log.model_copy(update={"event_type": "TradDraft"})
    with pytest.raises(ValueError, match="TradDraft"):
        analyze_draft(other, inputs)


def test_format_constants_override_the_global_settings() -> None:
    row = FormatConstants(
        tax_value=6,
        target_removal=3,
        target_curve_1=1,
        target_curve_2=7,
        target_curve_3=6,
        target_curve_4=5,
        target_curve_5=3,
        target_curve_6=2,
    )
    cfg = fitness_config(row)
    assert (cfg.tax_value, cfg.target_removal) == (6.0, 3)
    assert isinstance(cfg.tax_value, float)
    assert cfg.target_curve == {1: 1, 2: 7, 3: 6, 4: 5, 5: 3, 6: 2}
    assert cfg.synergy_weight == fx.FitnessConfig().synergy_weight  # global, untouched
