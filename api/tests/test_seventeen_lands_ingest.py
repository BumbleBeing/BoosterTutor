"""The 17Lands ingest's pure layer (development plan 2.3).

These are the important tests in the ingest. Every win rate here is computed
by us from raw game rows rather than read from 17Lands, so an arithmetic slip
would flow silently into every verdict the analysis makes. Each case is small
enough that the expected number can be worked out by hand; most are ported
from DraftDouble, where they were written against HOB.
"""

import datetime as dt
import uuid

from boostertutor.ingest import seventeen_lands as sl
from boostertutor.models import Base

DRAFT_HEADER = [
    "draft_id",
    "pack_number",
    "pick_number",
    "pick",
    "pack_card_Alpha",
    "pack_card_Beta",
]


# --------------------------------------------------------------------------
# The draft dump: ALSA and ATA
# --------------------------------------------------------------------------


def test_alsa_and_ata_by_hand() -> None:
    """Alpha is taken first in one draft and wheels to the third pick in another.

    Input positions are 0-indexed, as the real files are; expectations are
    1-based, as everything downstream is.

    d1 pack 1: Alpha is in the pack at pick 1 and taken there.
    d2 pack 1: Alpha sits in the pack at picks 1, 2 and 3, taken at 3.

    ALSA = mean last-seen pick = (1 + 3) / 2 = 2.0
    ATA  = mean taken pick     = (1 + 3) / 2 = 2.0
    """
    rows = [
        ["d1", "0", "0", "Alpha", "1", "1"],
        ["d2", "0", "0", "Beta", "1", "1"],
        ["d2", "0", "1", "Beta", "1", "0"],
        ["d2", "0", "2", "Alpha", "1", "0"],
    ]
    stats = sl.aggregate_draft_data(rows, DRAFT_HEADER)
    assert stats["Alpha"] == {"alsa": 2.0, "ata": 2.0, "seen_count": 2, "pick_count": 2}
    # Beta is marked in the pack only at pick 1 of each draft (the d2 pick-2
    # row has it taken but not marked), so it was last seen at pick 1 twice.
    # It was taken at picks 1 and 2 of d2.
    assert stats["Beta"]["alsa"] == 1.0
    assert stats["Beta"]["ata"] == 1.5


def test_the_same_pack_and_card_in_two_drafts_are_two_observations() -> None:
    rows = [["d1", "0", "4", "Alpha", "1", "0"], ["d2", "0", "8", "Beta", "1", "0"]]
    stats = sl.aggregate_draft_data(rows, DRAFT_HEADER)
    assert stats["Alpha"]["seen_count"] == 2
    assert stats["Alpha"]["alsa"] == 7.0  # (5 + 9) / 2, one-based, not the max


def test_zero_indexed_picks_come_out_one_based() -> None:
    """Pick 0 in the file is pick 1 everywhere else; a slip here is off by one everywhere."""
    stats = sl.aggregate_draft_data([["d1", "0", "0", "Alpha", "1", "0"]], DRAFT_HEADER)
    assert (stats["Alpha"]["ata"], stats["Alpha"]["alsa"]) == (1.0, 1.0)


# --------------------------------------------------------------------------
# The game dump: win rates
# --------------------------------------------------------------------------

GAME_HEADER = [
    "won",
    "main_colors",
    "deck_Alpha",
    "opening_hand_Alpha",
    "drawn_Alpha",
    "tutored_Alpha",
    "deck_Beta",
    "opening_hand_Beta",
    "drawn_Beta",
    "tutored_Beta",
]


def _rates(rows: list[list[str]]) -> tuple[dict, dict, dict]:
    overall, by_archetype, archetypes = sl.aggregate_game_data(rows, GAME_HEADER)
    return (
        {card: sl.card_rates(c) for card, c in overall.items()},
        {key: sl.card_rates(c) for key, c in by_archetype.items()},
        archetypes,
    )


def test_gih_gnd_and_iwd_by_hand() -> None:
    """Alpha is in the deck for 3 games: in hand in 2 (1 win), never drawn in 1 (a loss).

    GIH WR = 1/2 = 50.0, GND WR = 0/1 = 0.0, IWD = +50.0, GP WR = 1/3.
    """
    rows = [
        ["True", "BR", "1", "1", "0", "0", "1", "0", "0", "0"],
        ["False", "BR", "1", "0", "1", "0", "0", "0", "0", "0"],
        ["False", "WU", "1", "0", "0", "0", "1", "0", "1", "0"],
    ]
    overall, by_archetype, archetypes = _rates(rows)
    alpha = overall["Alpha"]
    assert (alpha["gp_games"], alpha["gih_games"], alpha["gnd_games"]) == (3, 2, 1)
    assert (alpha["gih_wr"], alpha["gnd_wr"], alpha["iwd"]) == (50.0, 0.0, 50.0)
    assert alpha["gp_wr"] == 100 / 3

    # In BR decks Alpha was in hand both times. In the WU game it sat in the
    # deck undrawn, which counts towards WU's GND but not its GIH.
    assert (
        by_archetype[("Alpha", "BR")]["gih_games"],
        by_archetype[("Alpha", "BR")]["gih_wr"],
    ) == (2, 50.0)
    assert by_archetype[("Alpha", "WU")]["gih_games"] == 0
    assert by_archetype[("Alpha", "WU")]["gnd_games"] == 1

    assert archetypes == {"BR": {"wins": 1, "games": 2}, "WU": {"wins": 0, "games": 1}}


def test_opening_hand_and_drawn_split_games_in_hand() -> None:
    """OH and GD partition GIH: an opening-hand copy wins over a later draw."""
    rows = [
        ["True", "BR", "2", "1", "1", "0", "0", "0", "0", "0"],  # in hand and drawn: OH
        ["False", "BR", "1", "0", "1", "0", "0", "0", "0", "0"],  # drawn only: GD
        [
            "True",
            "BR",
            "1",
            "0",
            "0",
            "1",
            "0",
            "0",
            "0",
            "0",
        ],  # tutored counts as drawn
    ]
    alpha = _rates(rows)[0]["Alpha"]
    assert (alpha["oh_games"], alpha["oh_wr"]) == (1, 100.0)
    assert (alpha["gd_games"], alpha["gd_wr"]) == (2, 50.0)
    assert alpha["gih_games"] == alpha["oh_games"] + alpha["gd_games"] == 3
    assert alpha["gnd_games"] == 0
    assert alpha["iwd"] is None  # never undrawn, so no GND rate to compare with


def test_a_card_only_in_the_sideboard_contributes_nothing() -> None:
    rows = [["True", "BR", "0", "0", "0", "0", "1", "1", "0", "0"]]
    overall, _, _ = _rates(rows)
    assert "Alpha" not in overall
    assert overall["Beta"]["gih_games"] == 1


def test_non_pair_decks_count_overall_but_in_no_archetype() -> None:
    rows = [
        ["True", "B", "1", "1", "0", "0", "0", "0", "0", "0"],
        ["True", "WUB", "1", "1", "0", "0", "0", "0", "0", "0"],
    ]
    overall, by_archetype, archetypes = _rates(rows)
    assert overall["Alpha"]["gih_games"] == 2
    assert by_archetype == {}
    assert archetypes == {}


def test_sorted_pair_normalizes_and_rejects_non_pairs() -> None:
    assert sl.sorted_pair("RW") == "WR"
    assert sl.sorted_pair("UB") == "UB"
    assert sl.sorted_pair("W") is None
    assert sl.sorted_pair("WUB") is None
    assert sl.sorted_pair("") is None


# --------------------------------------------------------------------------
# Rows, names and skipping
# --------------------------------------------------------------------------


def test_build_rows_resolves_front_face_names_and_reports_the_rest() -> None:
    alpha, back = uuid.UUID(int=1), uuid.UUID(int=2)
    resolve = {"alpha": alpha, "front": back}
    counts = sl._new_counts()
    counts.update(gp_games=4, gp_wins=2, gih_games=2, gih_wins=1)
    cards, archetype_cards, archetypes, unmatched = sl.build_rows(
        "hob",
        "PremierDraft",
        dt.date(2026, 10, 1),
        resolve,
        draft_stats={
            "Alpha": {"alsa": 3.0, "ata": 2.0, "seen_count": 5, "pick_count": 4},
            "Mystery": {},
        },
        overall={"Alpha": counts, "Front // Back": counts},
        by_archetype={("Alpha", "BR"): counts},
        archetypes={"BR": {"wins": 3, "games": 4}},
    )
    assert unmatched == ["Mystery"]
    by_id = {row["oracle_id"]: row for row in cards}
    assert by_id[alpha]["alsa"] == 3.0
    assert by_id[alpha]["gih_wr"] == 50.0
    assert by_id[back]["seen_count"] == 0  # in games but never seen in a logged pack
    assert by_id[alpha]["snapshot_date"] == dt.date(2026, 10, 1)
    assert archetype_cards[0]["archetype"] == "BR"
    assert archetypes == [
        {
            "set_code": "hob",
            "event_type": "PremierDraft",
            "snapshot_date": dt.date(2026, 10, 1),
            "archetype": "BR",
            "wins": 3,
            "games": 4,
            "win_rate": 75.0,
        }
    ]


def test_an_unchanged_dump_is_skipped_unless_forced() -> None:
    stamp = dt.datetime(2026, 10, 1, 13, 17, tzinfo=dt.UTC)
    assert sl.should_skip(stamp, stamp)
    assert not sl.should_skip(stamp, stamp, force=True)
    assert not sl.should_skip(stamp, stamp + dt.timedelta(days=1))
    assert not sl.should_skip(None, stamp)
    assert not sl.should_skip(stamp, None)


def test_the_two_dump_addresses() -> None:
    assert sl.game_data_url("hob").endswith(
        "/game_data/game_data_public.HOB.PremierDraft.csv.gz"
    )
    assert sl.draft_data_url("hob", "TradDraft").endswith(
        "/draft_data/draft_data_public.HOB.TradDraft.csv.gz"
    )


# --------------------------------------------------------------------------
# The schema
# --------------------------------------------------------------------------


def test_every_stats_table_is_keyed_by_snapshot() -> None:
    keys = {
        name: [c.name for c in Base.metadata.tables[name].primary_key.columns]
        for name in ("card_draft_stats", "card_archetype_stats", "archetype_stats")
    }
    assert keys == {
        "card_draft_stats": ["set_code", "event_type", "oracle_id", "snapshot_date"],
        "card_archetype_stats": [
            "set_code",
            "event_type",
            "oracle_id",
            "archetype",
            "snapshot_date",
        ],
        "archetype_stats": ["set_code", "event_type", "archetype", "snapshot_date"],
    }


def test_every_win_rate_travels_with_its_game_count() -> None:
    columns = set(Base.metadata.tables["card_draft_stats"].columns.keys())
    for outcome in ("gp", "oh", "gd", "gih", "gnd"):
        assert {f"{outcome}_wr", f"{outcome}_games"} <= columns
