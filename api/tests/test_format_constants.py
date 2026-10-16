"""The shape of `format_constants` (ADR 0013).

These assert the table's definition rather than its contents: there is no
test database in this project yet, so nothing here connects to Postgres.
What they protect is the part a migration can silently get wrong -- the
primary key, and the set of columns the fitness function will read.
"""

from boostertutor.models import Base, FormatConstants

TABLE = Base.metadata.tables["format_constants"]


def test_it_is_keyed_by_set_and_event_type() -> None:
    """Premier and Traditional Draft are different formats, not one."""
    assert [c.name for c in TABLE.primary_key.columns] == ["set_code", "event_type"]


def test_it_carries_every_format_level_constant() -> None:
    assert set(TABLE.columns.keys()) == {
        "set_code",
        "event_type",
        "format_avg_wr",
        "replacement_offset",
        "tax_value",
        "picks_per_pack",
        "target_creatures",
        "target_removal",
        *(f"target_curve_{mv}" for mv in range(1, 7)),
        # ADR 0028 s4's land targets.
        "land_target_low",
        "land_target_mid",
        "land_target_high",
        "land_low_below_mv",
        "land_high_from_mv",
        "source",
        "updated_at",
    }


def test_the_curve_is_six_columns_one_per_mana_value() -> None:
    """Structure, not data: the curve term clamps mana value to 1..6."""
    curve = [c.name for c in TABLE.columns if c.name.startswith("target_curve_")]
    assert sorted(curve) == [f"target_curve_{mv}" for mv in range(1, 7)]


def test_every_column_is_required() -> None:
    """A format with a missing constant is not a format we can score."""
    assert [c.name for c in TABLE.columns if c.nullable] == []


def test_provenance_is_recorded_per_row() -> None:
    assert FormatConstants.__tablename__ == "format_constants"
    assert "source" in TABLE.columns
