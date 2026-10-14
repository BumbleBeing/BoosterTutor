"""The Scryfall ingest's pure layer (development plan 2.2).

No network and no database: every function tested here takes plain data and
returns plain data. The upsert is checked by compiling its SQL for Postgres,
which is as far as it can go without a test database.
"""

import datetime as dt
import gzip
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql

from boostertutor.ingest import scryfall
from boostertutor.models import Base, Card

ORACLE = "11111111-1111-1111-1111-111111111111"
PRINT = "22222222-2222-2222-2222-222222222222"


def _raw(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "id": PRINT,
        "oracle_id": ORACLE,
        "name": "Test Bear",
        "mana_cost": "{1}{G}",
        "cmc": 2.0,
        "type_line": "Creature — Bear",
        "oracle_text": "Vigilance.",
        "colors": ["G"],
        "color_identity": ["G"],
        "power": "2",
        "toughness": "2",
        "layout": "normal",
        "keywords": ["Vigilance"],
        "set": "hob",
        "collector_number": "123",
        "rarity": "common",
        "image_uris": {"normal": "http://img/n.jpg", "art_crop": "http://img/a.jpg"},
        "arena_id": 999,
    }
    raw.update(overrides)
    return raw


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def test_sort_colors_writes_wubrg_order() -> None:
    assert scryfall.sort_colors(["R", "W"]) == "WR"
    assert scryfall.sort_colors(["G", "U", "B"]) == "UBG"
    assert scryfall.sort_colors([]) == ""
    assert scryfall.sort_colors(None) == ""


def test_parse_card_gives_a_card_row_and_a_print_row() -> None:
    card, printing = scryfall.parse_card(_raw())
    assert card["oracle_id"] == uuid.UUID(ORACLE)
    assert card["cmc"] == 2.0
    assert card["colors"] == "G"
    assert card["keywords"] == ["Vigilance"]  # a list: the column is JSONB
    assert printing["scryfall_id"] == uuid.UUID(PRINT)
    assert printing["oracle_id"] == card["oracle_id"]
    assert printing["rarity"] == "common"
    assert printing["arena_id"] == 999
    assert printing["image_art_crop"] == "http://img/a.jpg"


def test_parse_card_reads_double_faced_cards_from_their_faces() -> None:
    """Two-faced cards keep cost and text on the faces; neither may become NULL."""
    raw = _raw(
        name="Front // Back",
        layout="transform",
        type_line="Creature // Creature",
        color_identity=["U", "R"],
        card_faces=[
            {
                "mana_cost": "{2}{U}",
                "oracle_text": "Front text.",
                "colors": ["U"],
                "power": "1",
                "toughness": "3",
                "image_uris": {"normal": "http://img/front.jpg"},
            },
            {
                "mana_cost": "",
                "oracle_text": "Back text.",
                "colors": ["R"],
                "power": "4",
                "toughness": "4",
            },
        ],
    )
    for key in (
        "mana_cost",
        "oracle_text",
        "colors",
        "power",
        "toughness",
        "image_uris",
        "arena_id",
    ):
        del raw[key]
    card, printing = scryfall.parse_card(raw)
    assert card["oracle_text"] == "Front text. // Back text."
    assert card["mana_cost"] == "{2}{U}"  # the empty back face adds nothing
    assert card["colors"] == "UR"  # both faces' colours
    assert card["power"] == "1 // 4"
    assert printing["image_normal"] == "http://img/front.jpg"
    assert printing["arena_id"] is None  # never on Arena: a null, not a crash


def test_parse_card_keeps_non_numeric_power_as_text() -> None:
    card, _ = scryfall.parse_card(_raw(power="*", toughness="1+*"))
    assert (card["power"], card["toughness"]) == ("*", "1+*")


def test_parse_set_marks_only_booster_set_types_draftable() -> None:
    expansion = scryfall.parse_set(
        {
            "code": "hob",
            "name": "The Hobbit",
            "released_at": "2026-08-14",
            "set_type": "expansion",
        }
    )
    assert expansion == {
        "set_code": "hob",
        "name": "The Hobbit",
        "released_at": dt.date(2026, 8, 14),
        "set_type": "expansion",
        "is_draftable": True,
    }
    tokens = scryfall.parse_set(
        {"code": "thob", "name": "Hobbit Tokens", "set_type": "token"}
    )
    assert tokens["is_draftable"] is False
    assert tokens["released_at"] is None


# --------------------------------------------------------------------------
# Choosing sets, and the bulk file
# --------------------------------------------------------------------------

SETS = [
    {
        "code": "nxt",
        "set_type": "expansion",
        "released_at": "2026-11-20",
    },  # not out yet
    {"code": "hob", "set_type": "expansion", "released_at": "2026-08-14"},
    {
        "code": "hoc",
        "set_type": "commander",
        "released_at": "2026-08-14",
    },  # not drafted
    {"code": "cor", "set_type": "core", "released_at": "2026-06-01"},
    {"code": "inn", "set_type": "draft_innovation", "released_at": "2026-03-01"},
    {"code": "old", "set_type": "expansion", "released_at": "2025-11-01"},
    {"code": "ymm", "set_type": "alchemy", "released_at": "2026-09-01"},  # not drafted
]


def test_recent_draftable_sets_are_released_booster_sets_newest_first() -> None:
    assert scryfall.recent_draftable_sets(SETS, dt.date(2026, 10, 14), 3) == [
        "hob",
        "cor",
        "inn",
    ]


def test_a_set_released_today_counts() -> None:
    assert scryfall.recent_draftable_sets(SETS, dt.date(2026, 11, 20), 1) == ["nxt"]


def test_bulk_entry_prefers_jsonl_and_reads_the_update_time() -> None:
    index = {
        "data": [
            {"type": "oracle_cards", "jsonl_download_uri": "http://x/oracle.jsonl.gz"},
            {
                "type": "default_cards",
                "jsonl_download_uri": "http://x/default.jsonl.gz",
                "download_uri": "http://x/default.json",
                "updated_at": "2026-10-14T09:04:55.123+00:00",
            },
        ]
    }
    url, updated = scryfall.bulk_entry(index)
    assert url == "http://x/default.jsonl.gz"
    assert updated == dt.datetime(2026, 10, 14, 9, 4, 55, 123000, tzinfo=dt.UTC)


def test_bulk_entry_names_a_missing_type() -> None:
    with pytest.raises(ValueError, match="default_cards"):
        scryfall.bulk_entry({"data": []})


def test_iter_cards_keeps_wanted_sets_and_drops_tokens(tmp_path: Path) -> None:
    lines = [
        _raw(),
        _raw(id="33333333-3333-3333-3333-333333333333", set="xyz"),  # another set
        _raw(id="44444444-4444-4444-4444-444444444444", layout="token"),
        _raw(id="55555555-5555-5555-5555-555555555555", oracle_id=None),  # meld piece
    ]
    path = tmp_path / "default-cards.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write("\n".join(json.dumps(line) for line in lines))
    assert [c["id"] for c in scryfall.iter_cards(path, ["HOB"])] == [PRINT]


def test_rows_for_deduplicates_cards_but_keeps_every_printing() -> None:
    """A showcase reprint is a second printing of the same card."""
    showcase = _raw(id="66666666-6666-6666-6666-666666666666", collector_number="301")
    cards, prints = scryfall.rows_for([_raw(), showcase])
    assert len(cards) == 1
    assert [p["collector_number"] for p in prints] == ["123", "301"]


# --------------------------------------------------------------------------
# Skipping, and the upsert
# --------------------------------------------------------------------------

STAMP = dt.datetime(2026, 10, 14, 9, 0, tzinfo=dt.UTC)


def test_an_unchanged_file_and_scope_is_skipped() -> None:
    assert scryfall.should_skip((STAMP, "cor,hob,inn"), STAMP, "cor,hob,inn")


def test_a_new_file_a_new_scope_or_force_runs_again() -> None:
    assert not scryfall.should_skip(
        (STAMP, "hob"), STAMP + dt.timedelta(hours=12), "hob"
    )
    assert not scryfall.should_skip((STAMP, "hob"), STAMP, "cor,hob")
    assert not scryfall.should_skip((STAMP, "hob"), STAMP, "hob", force=True)
    assert not scryfall.should_skip(None, STAMP, "hob")  # never run
    assert not scryfall.should_skip(
        (STAMP, "hob"), None, "hob"
    )  # upstream gives no date


def test_upsert_updates_every_column_but_the_key() -> None:
    card, _ = scryfall.parse_card(_raw())
    sql = str(scryfall.upsert(Card, [card]).compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (oracle_id) DO UPDATE SET" in sql
    assert "name = excluded.name" in sql
    assert "oracle_id = excluded.oracle_id" not in sql


# --------------------------------------------------------------------------
# The schema this ingest writes
# --------------------------------------------------------------------------


def test_card_prints_carry_an_indexed_nullable_arena_id() -> None:
    column = Base.metadata.tables["card_prints"].c.arena_id
    assert column.nullable
    assert column.index


def test_ingest_runs_record_source_freshness_and_scope() -> None:
    table = Base.metadata.tables["ingest_runs"]
    assert set(table.columns.keys()) == {
        "id",
        "source",
        "ran_at",
        "source_url",
        "upstream_updated_at",
        "scope",
        "row_count",
        "notes",
    }
