"""Load the hand-authored tag taxonomy from its JSON file into Postgres.

    uv run python -m boostertutor.ingest taxonomy [--sets hob]

The file (`api/data/taxonomy/{set}.json`) is the system of record; see
`models/tags.py`. It is written by DraftDouble's tagger, keyed by card
*name* so a diff is readable:

    {"format_version": 2, "set_code": "hob",
     "tags":      [{"name", "kind", "notes"}, ...],
     "tag_pairs": [{"enabler", "payoff", "coefficient", "decay", "notes"}, ...],
     "card_tags": {"Card Name": ["tag", ...], ...},
     "source_kinds": {"kind": {"color_weight", "land_weight",
                               "min_mana_value", "basis", "notes"}, ...},
     "mana_sources": {"Card Name": {"kind", "colors", "expected",
                                    "notes", <overrides>}, ...}}

Version 2 added the last two sections, the set's Fixers (ADR 0028).
`source_kinds` is optional: the kinds in `defaults/source_kinds.json` apply
to every set, and a set lists only a kind it adds or redefines, in full.
A `mana_sources` entry may override its kind's `color_weight`,
`land_weight` or `min_mana_value`, and must then say why in `notes`.

Loading **replaces** the set's taxonomy rather than merging, so a tag the
file no longer has is removed. Unlike DraftDouble's loader it **fails** on
anything it cannot place, an unknown card name included, and loads nothing:
a silently dropped tag would quietly change how picks score.

Run it after the Scryfall ingest, whose cards the names are matched to.
"""

import json
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from ..analysis.mana import BASICS
from ..config import settings
from ..format_inputs import name_index
from ..models import CardManaSource, CardTag, Tag, TagPair
from ..models.tags import TAG_KINDS
from ..parsing.names import name_key
from .runs import recorded_run

SOURCE = "taxonomy"

# Bump when the file layout changes in a way an older reader would misread.
FORMAT_VERSION = 2

# What a source kind and a mana source entry may hold (ADR 0028).
KIND_WEIGHTS = ("color_weight", "land_weight", "min_mana_value")
KIND_FIELDS = {*KIND_WEIGHTS, "per_expected", "basis", "notes"}
ENTRY_FIELDS = {"kind", "colors", "expected", "notes", *KIND_WEIGHTS}


class TaxonomyError(ValueError):
    """The file cannot be loaded as it stands. Lists every problem at once."""

    def __init__(self, set_code: str, problems: list[str]) -> None:
        super().__init__(
            f"{set_code} taxonomy has {len(problems)} problem(s):\n  "
            + "\n  ".join(problems)
        )
        self.problems = problems


def taxonomy_path(set_code: str) -> Path:
    return settings.taxonomy_dir / f"{set_code}.json"


def default_source_kinds() -> dict[str, dict[str, Any]]:
    """The source kinds every set starts from (ADR 0028 s2)."""
    kinds: dict[str, dict[str, Any]] = json.loads(
        (settings.taxonomy_dir / "defaults" / "source_kinds.json").read_text()
    )
    return kinds


def rows_for(
    payload: dict[str, Any],
    names: Mapping[str, uuid.UUID],
    default_kinds: Mapping[str, dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """The rows for `tags`, `tag_pairs`, `card_tags` and `card_mana_sources`.

    Raises `TaxonomyError` listing every problem instead. `names` maps
    `name_key(name)` to oracle id for the set's cards. Pure but for reading
    the shared source kinds when `default_kinds` is not given. Checks what
    the database cannot: that the diagonal of `tag_pairs` belongs to
    `self_payoff` tags and only to them, that every card name is a card we
    know, and that every Fixer can be placed.
    """
    set_code = str(payload.get("set_code", "?"))
    if payload.get("format_version") != FORMAT_VERSION:
        version = payload.get("format_version")
        raise TaxonomyError(
            set_code, [f"format_version is {version!r}, expected {FORMAT_VERSION}"]
        )
    problems: list[str] = []

    kinds: dict[str, str] = {}
    for tag in payload["tags"]:
        if tag["kind"] not in TAG_KINDS:
            problems.append(f"tag {tag['name']!r} has unknown kind {tag['kind']!r}")
        if tag["name"] in kinds:
            problems.append(f"tag {tag['name']!r} is listed twice")
        kinds[tag["name"]] = tag["kind"]

    for pair in payload["tag_pairs"]:
        enabler, payoff = pair["enabler"], pair["payoff"]
        edge = f"pair {enabler} -> {payoff}"
        for end in (enabler, payoff):
            if end not in kinds:
                problems.append(f"{edge}: no tag named {end!r}")
        on_diagonal = enabler == payoff
        if on_diagonal and kinds.get(enabler, "self_payoff") != "self_payoff":
            problems.append(f"{edge}: only a self_payoff tag may pair with itself")
        if not on_diagonal and "self_payoff" in (kinds.get(enabler), kinds.get(payoff)):
            problems.append(f"{edge}: a self_payoff tag pairs only with itself")
        if not 0 <= pair.get("decay", 0.5) <= 1:
            problems.append(f"{edge}: decay must be between 0 and 1")

    card_rows: list[dict[str, Any]] = []
    for card_name, tags in payload["card_tags"].items():
        oracle_id = names.get(name_key(card_name))
        if oracle_id is None:
            problems.append(f"card {card_name!r} is not in {set_code}'s card list")
            continue
        for tag in tags:
            if tag not in kinds:
                problems.append(f"card {card_name!r}: no tag named {tag!r}")
            card_rows.append({"oracle_id": oracle_id, "set_code": set_code, "tag": tag})

    source_kinds = {**(default_kinds or default_source_kinds())}
    for name, kind in (payload.get("source_kinds") or {}).items():
        problems += _kind_problems(name, kind)
        source_kinds[name] = kind
    mana_rows: list[dict[str, Any]] = []
    for card_name, entry in payload["mana_sources"].items():
        row, entry_problems = _mana_source_row(card_name, entry, source_kinds)
        problems += [f"mana source {card_name!r}: {p}" for p in entry_problems]
        oracle_id = names.get(name_key(card_name))
        if oracle_id is None:
            problems.append(
                f"mana source {card_name!r} is not in {set_code}'s card list"
            )
        elif row is not None:
            mana_rows.append({**row, "oracle_id": oracle_id, "set_code": set_code})

    if problems:
        raise TaxonomyError(set_code, problems)

    return {
        "tags": [
            {
                "set_code": set_code,
                "name": t["name"],
                "kind": t["kind"],
                "notes": t.get("notes"),
            }
            for t in payload["tags"]
        ],
        "tag_pairs": [
            {
                "set_code": set_code,
                "enabler": p["enabler"],
                "payoff": p["payoff"],
                "coefficient": p["coefficient"],
                # A file from before ADR 0009 has no decay; 0.5 is its default.
                "decay": p.get("decay", 0.5),
                "notes": p.get("notes"),
            }
            for p in payload["tag_pairs"]
        ],
        "card_tags": card_rows,
        "card_mana_sources": mana_rows,
    }


def _kind_problems(name: str, kind: dict[str, Any]) -> list[str]:
    problems = [
        f"source kind {name!r} has no {field}"
        for field in KIND_WEIGHTS
        if field not in kind
    ]
    unknown = sorted(set(kind) - KIND_FIELDS)
    if unknown:
        problems.append(f"source kind {name!r}: unknown field(s) {', '.join(unknown)}")
    return problems


def _mana_source_row(
    card_name: str, entry: dict[str, Any], kinds: Mapping[str, dict[str, Any]]
) -> tuple[dict[str, Any] | None, list[str]]:
    """One Fixer's resolved row (without its ids), and what is wrong with it.

    The weights are resolved here, once, so the analysis reads finished
    numbers: the kind's figures, a Treasure maker's colour weight scaled by
    its expected Treasures and capped at one source, then any override.
    """
    problems: list[str] = []
    kind = kinds.get(entry.get("kind", ""))
    colors = str(entry.get("colors", ""))
    overrides = [f for f in KIND_WEIGHTS if f in entry]

    if overrides and not entry.get("notes"):
        problems.append(f"overrides {', '.join(overrides)} without notes saying why")
    if kind is None:
        problems.append(f"unknown kind {entry.get('kind')!r}")
    if colors != BASICS and (not colors or set(colors) - set("WUBRG")):
        problems.append(f"colors must be 'basics' or WUBRG letters, not {colors!r}")
    per_expected = bool(kind and kind.get("per_expected"))
    if per_expected and "expected" not in entry:
        problems.append(f"a {entry['kind']} entry needs expected")
    if kind is not None and not per_expected and "expected" in entry:
        problems.append("only a treasure entry has expected")
    unknown = sorted(set(entry) - ENTRY_FIELDS)
    if unknown:
        problems.append(f"unknown field(s) {', '.join(unknown)}")
    if problems or kind is None:
        return None, problems

    color_weight = float(kind["color_weight"])
    if per_expected:
        color_weight = min(1.0, color_weight * float(entry["expected"]))
    return {
        "kind": entry["kind"],
        # Sorted WUBRG, as `cards.colors` is stored.
        "colors": colors
        if colors == BASICS
        else "".join(c for c in "WUBRG" if c in colors),
        "expected": entry.get("expected"),
        "color_weight": float(entry.get("color_weight", color_weight)),
        "land_weight": float(entry.get("land_weight", kind["land_weight"])),
        "min_mana_value": int(entry.get("min_mana_value", kind["min_mana_value"])),
        "notes": entry.get("notes"),
    }, problems


def load(session: Session, set_codes: list[str]) -> None:
    """Replace each set's taxonomy with its file. One transaction per set."""
    for set_code in set_codes:
        with recorded_run(session, SOURCE, scope=set_code) as record:
            path = taxonomy_path(set_code)
            record.source_url = str(path.relative_to(settings.taxonomy_dir.parents[1]))
            payload = json.loads(path.read_text())
            if payload.get("set_code") != set_code:
                raise TaxonomyError(
                    set_code, [f"{path.name} says it is {payload.get('set_code')!r}"]
                )
            rows = rows_for(payload, name_index(session, set_code))

            # Deleting the tags cascades to tag_pairs and card_tags.
            session.execute(delete(Tag).where(Tag.set_code == set_code))
            session.execute(
                delete(CardManaSource).where(CardManaSource.set_code == set_code)
            )
            session.execute(insert(Tag), rows["tags"])
            if rows["tag_pairs"]:
                session.execute(insert(TagPair), rows["tag_pairs"])
            if rows["card_tags"]:
                session.execute(insert(CardTag), rows["card_tags"])
            if rows["card_mana_sources"]:
                session.execute(insert(CardManaSource), rows["card_mana_sources"])

            record.row_count = sum(len(r) for r in rows.values())
            record.notes = (
                f"{len(rows['tags'])} tags, {len(rows['tag_pairs'])} pairs, "
                f"{len(rows['card_tags'])} card tags, "
                f"{len(rows['card_mana_sources'])} mana sources"
            )
            print(f"{set_code}: {record.notes}")


def available_sets() -> list[str]:
    """Every set with a taxonomy file."""
    return sorted(p.stem for p in settings.taxonomy_dir.glob("*.json"))
