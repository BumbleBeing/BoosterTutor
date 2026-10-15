"""The synergy baseline (ADR 0017): measuring it, and reading it back.

Every expected number here is worked out by hand from rows small enough to
check with a pencil.
"""

import uuid

import pytest

from boostertutor.analysis.draft import synergy_expectations
from boostertutor.ingest import synergy_baseline as sb
from boostertutor.parsing.names import name_key

ARTIFACT, SAC, LEGION = (uuid.UUID(int=i) for i in (1, 2, 3))
NAMES = {
    name_key(n): oid
    for n, oid in (("Map", ARTIFACT), ("Outlet", SAC), ("Legion", LEGION))
}
TAGS = {ARTIFACT: {"artifact"}, SAC: {"sac_outlet"}, LEGION: {"legion"}}
EDGES = [
    {"enabler": "artifact", "payoff": "sac_outlet", "coefficient": 0.3, "decay": 0.5},
    {"enabler": "legion", "payoff": "legion", "coefficient": 0.5, "decay": 1.0},
]
HEADER = [
    "draft_id",
    "pack_number",
    "pick_number",
    "pack_card_Map",
    "pack_card_Outlet",
    "pack_card_Legion",
    "pool_Map",
    "pool_Outlet",
    "pool_Legion",
]


def test_each_edge_is_walked_from_both_ends_except_the_diagonal() -> None:
    walked = [(on_card, comp) for _, on_card, comp in sb.directions(EDGES)]
    assert walked == [
        ("artifact", "sac_outlet"),
        ("sac_outlet", "artifact"),
        ("legion", "legion"),  # once: both ends are the same read
    ]


def test_measure_counts_complements_in_the_pool_by_hand() -> None:
    """Two picks of one draft, both in pack 1 (0 in the file).

    Pick 1: Map and Outlet in the pack, an empty pool.
      Map    sits on `artifact`, counts `sac_outlet` in the pool: 0.
      Outlet sits on `sac_outlet`, counts `artifact`: 0.
    Pick 2: Outlet and Legion in the pack, two Maps and a Legion in the pool.
      Outlet counts `artifact`: 2 (two copies are two).
      Legion counts `legion`: 1.
    """
    rows = [
        ["d1", "0", "0", "1", "1", "0", "0", "0", "0"],
        ["d1", "0", "1", "0", "1", "1", "2", "0", "1"],
    ]
    histogram = sb.measure(HEADER, rows, NAMES, TAGS, EDGES)
    assert histogram == {
        (ARTIFACT, 1, "artifact", "sac_outlet", "artifact", 0): 1,
        (SAC, 1, "artifact", "sac_outlet", "sac_outlet", 0): 1,
        (SAC, 1, "artifact", "sac_outlet", "sac_outlet", 2): 1,
        (LEGION, 1, "legion", "legion", "legion", 1): 1,
    }


def test_measure_can_stop_after_a_sample_of_drafts() -> None:
    rows = [
        ["d1", "0", "0", "1", "0", "0", "0", "0", "0"],
        ["d2", "0", "0", "1", "0", "0", "0", "0", "0"],
    ]
    histogram = sb.measure(HEADER, rows, NAMES, TAGS, EDGES, max_drafts=1)
    assert sum(histogram.values()) == 1


def test_a_dump_column_for_an_unknown_card_is_ignored() -> None:
    header = [*HEADER, "pack_card_Mystery"]
    rows = [["d1", "0", "0", "1", "0", "0", "0", "0", "0", "1"]]
    assert sum(sb.measure(header, rows, NAMES, TAGS, EDGES).values()) == 1


def _row(n: int, observations: int) -> dict[str, object]:
    return {
        "oracle_id": SAC,
        "pack_number": 1,
        "enabler": "artifact",
        "payoff": "sac_outlet",
        "tag_on_card": "sac_outlet",
        "complement_count": n,
        "observations": observations,
    }


def test_expectations_average_n_eff_over_every_appearance() -> None:
    """Outlet seen 4 times: with 0, 0, 1 and 3 artifacts in the pool.

    At decay 0.5, n_eff is 0, 0, 1 and 1 + 0.5 + 0.25 = 1.75.
    E[n_eff] = (0 + 0 + 1 + 1.75) / 4 = 0.6875. The n = 0 rows count in the
    denominator; leaving them out would give 1.375 and make pools look poor.
    """
    rows = [_row(0, 2), _row(1, 1), _row(3, 1)]
    key = (SAC, 1, "artifact", "sac_outlet", "sac_outlet")
    assert synergy_expectations(rows, EDGES) == {key: pytest.approx(0.6875)}


def test_expectations_follow_the_edge_s_current_decay() -> None:
    """The point of storing counts: re-tuning decay needs no re-measurement."""
    rows = [_row(0, 2), _row(1, 1), _row(3, 1)]
    no_decay = [{**EDGES[0], "decay": 1.0}]
    (expected,) = synergy_expectations(rows, no_decay).values()
    assert expected == pytest.approx((0 + 0 + 1 + 3) / 4)


def test_expectations_skip_an_edge_deleted_since_measuring() -> None:
    assert synergy_expectations([_row(1, 5)], EDGES[1:]) == {}
