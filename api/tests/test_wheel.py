"""Wheel analysis (analysis/wheel.py): what came back, and what the table took."""

import uuid
from typing import Any

import pytest

from boostertutor.analysis.wheel import wheel_analysis
from boostertutor.schemas import DraftLog, Pick
from boostertutor.schemas.draft_analysis import DraftAnalysis

# A pack of nine is the smallest with a wheel: pick 1's pack comes back at
# pick 9 holding one card. Cards are numbered; pack p's cards are
# 100 * p + (0..8), so every card is distinct and easy to name.


def oid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


def _nine_card_draft(returned: int = 104) -> DraftLog:
    """Three packs of nine. In each pack the drafter takes the first card.

    Pack 1, pick 1 opens 100-108 and takes 100. The pack comes back at
    pick 9 holding `returned` (104 by default); the other seven drafters
    took the rest. The packs in between are filler the drafter never sees
    again (and so never wheel-checks).
    """
    picks: list[Pick] = []
    pool: list[uuid.UUID] = []
    for pack in (1, 2, 3):
        for pick in range(1, 10):
            if pick == 1:
                cards = [oid(100 * pack + i) for i in range(9)]
            elif pick == 9:
                cards = [oid(returned + 100 * (pack - 1))]
            else:  # someone else's pack, 10 - pick cards left in it
                cards = [oid(10_000 * pack + 100 * pick + i) for i in range(10 - pick)]
            picked = cards[0]
            picks.append(
                Pick(
                    pack_number=pack,
                    pick_number=pick,
                    pack_cards=cards,
                    picked=picked,
                    pool_before=list(pool),
                )
            )
            pool.append(picked)
    return DraftLog(
        set_code="hob",
        event_type="PremierDraft",
        drafted_at=None,
        source="arena",
        picks=picks,
    )


def _cards(log: DraftLog, colors: dict[int, str]) -> dict[uuid.UUID, dict[str, Any]]:
    every = {c for p in log.picks for c in p.pack_cards}
    return {c: {"colors": colors.get(c.int, "")} for c in every}


def test_a_nine_card_pack_wheels_once_by_hand() -> None:
    """Pack 1: opened 100-108, took 100, and 104 came back at pick 9.

    So the table took the other seven: 101, 102, 103, 105, 106, 107, 108.
    104 is green with a 58.0 win rate against a 56.0 average: a good card
    wheeled, which is the signal.
    """
    log = _nine_card_draft()
    colors = {104: "G", 101: "W", 102: "W", 103: "WU", 105: "B"}
    wheels = wheel_analysis(
        log,
        _cards(log, colors),
        gih_wr={oid(104): 58.0, oid(101): 60.0},
        alsa={oid(104): 2.1},
        format_avg_wr=56.0,
    )
    assert [w.pack_number for w in wheels] == [1, 2, 3]
    (lap,) = wheels[0].laps
    assert (lap.first_pick, lap.returned_at) == (1, 9)
    assert [c.oracle_id for c in lap.wheeled] == [oid(104)]
    back = lap.wheeled[0]
    assert (back.gih_wr, back.alsa, back.above_average) == (58.0, 2.1, True)
    assert sorted(c.oracle_id.int for c in lap.taken_by_table) == [
        101,
        102,
        103,
        105,
        106,
        107,
        108,
    ]

    by_color = {s.color: s for s in wheels[0].colors}
    assert by_color["G"].good_cards_wheeled == 1
    assert by_color["G"].best_wheeled == oid(104)
    # 103 is white-blue, so it counts once for each.
    assert (by_color["W"].cards_taken_by_table, by_color["U"].cards_taken_by_table) == (
        3,
        1,
    )
    assert by_color["B"].cards_taken_by_table == 1
    assert by_color["W"].good_cards_wheeled == 0
    assert by_color["W"].best_wheeled is None


def test_a_card_with_no_win_rate_is_never_good() -> None:
    log = _nine_card_draft()
    wheels = wheel_analysis(log, _cards(log, {104: "G"}), {}, {}, format_avg_wr=56.0)
    assert not wheels[0].laps[0].wheeled[0].above_average


def test_a_card_that_never_was_in_the_pack_cannot_come_back() -> None:
    """If pick 9 holds a card pick 1's pack never had, the table was not eight
    seats or the log is wrong. Nothing is reported rather than a false wheel."""
    log = _nine_card_draft(returned=999)
    with pytest.raises(ValueError, match="pick 9 holds cards pick 1 did not"):
        wheel_analysis(log, _cards(log, {}), {}, {}, format_avg_wr=56.0)


def test_the_drafter_s_own_pick_cannot_come_back() -> None:
    log = _nine_card_draft(returned=100)  # 100 was taken at pick 1
    with pytest.raises(ValueError):
        wheel_analysis(log, _cards(log, {}), {}, {}, format_avg_wr=56.0)


# --------------------------------------------------------------------------
# The real draft (fixtures shared with test_draft_analysis.py)
# --------------------------------------------------------------------------


def test_the_real_draft_wheels_six_laps_a_pack(analysis: DraftAnalysis) -> None:
    """A 14-card pack: picks 1-6 come back at 9-14, each eight cards lighter."""
    for wheel in analysis.wheels:
        assert [(lap.first_pick, lap.returned_at) for lap in wheel.laps] == [
            (p, p + 8) for p in range(1, 7)
        ]
        for lap in wheel.laps:
            assert len(lap.taken_by_table) == 7  # one per other drafter
            assert len(lap.wheeled) == 14 - (lap.returned_at - 1)


def test_the_real_p1p1_wheel_by_hand(
    analysis: DraftAnalysis, names: dict[str, uuid.UUID]
) -> None:
    """Worked out by hand from the payload, and matching 17Lands' own list of
    what went missing (see test_seventeen_lands_draft.py)."""
    lap = analysis.wheels[0].laps[0]
    came_back = {
        "elven raft-steerer",
        "front porch sentries",
        "ordinary bear",
        "old thrush",
        "goblin-town",
        "hobbit hole",
    }
    taken = {
        "elven passage",
        "lakeshore apothecary",
        "large bear",
        "ori, keeper of songs",
        "pinecone strike",
        "smaug's fury",
        "troop of ponies",
    }
    assert {c.oracle_id for c in lap.wheeled} == {names[n] for n in came_back}
    assert {c.oracle_id for c in lap.taken_by_table} == {names[n] for n in taken}
