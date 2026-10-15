"""Load the hand-authored tag taxonomy from its JSON file into Postgres.

    uv run python -m boostertutor.ingest taxonomy [--sets hob]

The file (`api/data/taxonomy/{set}.json`) is the system of record; see
`models/tags.py`. It is written by DraftDouble's tagger, keyed by card
*name* so a diff is readable:

    {"format_version": 1, "set_code": "hob",
     "tags":      [{"name", "kind", "notes"}, ...],
     "tag_pairs": [{"enabler", "payoff", "coefficient", "decay", "notes"}, ...],
     "card_tags": {"Card Name": ["tag", ...], ...}}

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

from ..config import settings
from ..drafts import name_index
from ..models import CardTag, Tag, TagPair
from ..models.tags import TAG_KINDS
from ..parsing.names import name_key
from .runs import recorded_run

SOURCE = "taxonomy"

# Bump when the file layout changes in a way an older reader would misread.
FORMAT_VERSION = 1


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


def rows_for(
    payload: dict[str, Any], names: Mapping[str, uuid.UUID]
) -> dict[str, list[dict[str, Any]]]:
    """The rows for `tags`, `tag_pairs` and `card_tags`, or `TaxonomyError`.

    Pure. `names` maps `name_key(name)` to oracle id for the set's cards.
    Checks what the database cannot: that the diagonal of `tag_pairs`
    belongs to `self_payoff` tags and only to them, and that every card
    name is a card we know.
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
    }


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
            session.execute(insert(Tag), rows["tags"])
            if rows["tag_pairs"]:
                session.execute(insert(TagPair), rows["tag_pairs"])
            if rows["card_tags"]:
                session.execute(insert(CardTag), rows["card_tags"])

            record.row_count = sum(len(r) for r in rows.values())
            record.notes = (
                f"{len(rows['tags'])} tags, {len(rows['tag_pairs'])} pairs, "
                f"{len(rows['card_tags'])} card tags"
            )
            print(f"{set_code}: {record.notes}")


def available_sets() -> list[str]:
    """Every set with a taxonomy file."""
    return sorted(p.stem for p in settings.taxonomy_dir.glob("*.json"))
