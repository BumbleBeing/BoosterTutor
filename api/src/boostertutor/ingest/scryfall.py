"""Scryfall ingest: every card and printing in the recent draftable sets.

Development plan 2.2, ported from DraftDouble's `ingest/scryfall.py`, which
was proven against HOB. Two things about Scryfall's bulk data that differ
from what older docs (and the plan) describe, both confirmed in DraftDouble:

  * The bulk index advertises `jsonl_download_uri`: newline-delimited JSON,
    gzipped, about 78 MB. We stream it line by line, so no extra dependency
    (the plan suggested `ijson`) and never more than one card in memory.
  * `api.scryfall.com` rejects requests without an `Accept` header
    (see `fetching.py`).

Run it with:

    uv run python -m boostertutor.ingest scryfall              # 3 most recent draftable sets
    uv run python -m boostertutor.ingest scryfall --sets hob   # exactly these sets

Everything above `load` is pure (no network, no database, no clock) and is
tested directly. `load` does the I/O.
"""

import datetime as dt
import gzip
import json
import re
import uuid
from collections.abc import Callable, Collection, Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Card, CardPrint, CardSet, IngestRun
from .fetching import fetch_json_bytes, fetch_to_file

BULK_INDEX_URL = "https://api.scryfall.com/bulk-data"
SETS_URL = "https://api.scryfall.com/sets"
SOURCE = "scryfall"

# The set types that get draft boosters. Scryfall also lists commander decks,
# promos, tokens, Alchemy rebalances and so on, none of which are drafted.
DRAFTABLE_SET_TYPES = frozenset({"expansion", "core", "draft_innovation"})

# Layouts that appear in bulk data but never in a booster. Letting them in
# would quietly add tokens and art cards to every pool the analysis reads.
EXCLUDED_LAYOUTS = frozenset({"token", "double_faced_token", "emblem", "art_series"})

WUBRG = "WUBRG"

# Rows per INSERT. Postgres allows 65,535 bound parameters per statement;
# 1,000 cards at 12 columns stays far below that.
BATCH_SIZE = 1000


# --------------------------------------------------------------------------
# Parsing (pure)
# --------------------------------------------------------------------------


def sort_colors(colors: Iterable[str] | None) -> str:
    """Scryfall gives colour arrays; we store sorted WUBRG letters.

    "" is colourless, "U" mono-blue, "BR" gold. 17Lands names colour pairs the
    same way, so archetype joins become a string comparison.
    """
    if not colors:
        return ""
    wanted = set(colors)
    return "".join(c for c in WUBRG if c in wanted)


def _face_value(raw: dict[str, Any], key: str) -> str | None:
    """A field that lives on the card, or (for two-faced cards) on its faces.

    Double-faced cards put mana cost, text, power and toughness on each face.
    The faces are joined with " // ", as Scryfall writes the combined name,
    so nothing silently becomes NULL. Empty values are skipped: the back of a
    transform card has mana cost "", which would leave a trailing " // ".
    """
    if raw.get(key) is not None:
        return str(raw[key])
    parts = [str(face[key]) for face in raw.get("card_faces") or [] if face.get(key)]
    return " // ".join(parts) if parts else None


def _face_colors(raw: dict[str, Any]) -> list[str]:
    """The union of the faces' colours, for layouts with no top-level `colors`."""
    colors: set[str] = set()
    for face in raw.get("card_faces") or []:
        colors.update(face.get("colors") or [])
    return sorted(colors)


def _image(raw: dict[str, Any], size: str) -> str | None:
    """An image URL, from the card or (for two-faced cards) its front face."""
    if uris := raw.get("image_uris"):
        return uris.get(size)
    for face in raw.get("card_faces") or []:
        if uris := face.get("image_uris"):
            return uris.get(size)
    return None


def parse_card(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """One Scryfall card object as (a `cards` row, a `card_prints` row)."""
    card = {
        "oracle_id": uuid.UUID(raw["oracle_id"]),
        "name": raw["name"],
        "mana_cost": _face_value(raw, "mana_cost"),
        "cmc": float(raw.get("cmc") or 0.0),
        "type_line": raw.get("type_line") or "",
        "oracle_text": _face_value(raw, "oracle_text"),
        "colors": sort_colors(raw.get("colors") or _face_colors(raw)),
        "color_identity": sort_colors(raw.get("color_identity")),
        "power": _face_value(raw, "power"),
        "toughness": _face_value(raw, "toughness"),
        "layout": raw.get("layout") or "normal",
        "keywords": list(raw.get("keywords") or []),
    }
    printing = {
        "scryfall_id": uuid.UUID(raw["id"]),
        "oracle_id": card["oracle_id"],
        "set_code": raw["set"],
        "collector_number": raw.get("collector_number") or "",
        "rarity": raw.get("rarity") or "",
        "image_normal": _image(raw, "normal"),
        "image_art_crop": _image(raw, "art_crop"),
        "arena_id": raw.get("arena_id"),
    }
    return card, printing


def parse_set(raw: dict[str, Any]) -> dict[str, Any]:
    """One entry of Scryfall's set list as a `sets` row."""
    released = raw.get("released_at")
    return {
        "set_code": raw["code"],
        "name": raw["name"],
        "released_at": dt.date.fromisoformat(released) if released else None,
        "set_type": raw.get("set_type") or "",
        "is_draftable": raw.get("set_type") in DRAFTABLE_SET_TYPES,
    }


def recent_draftable_sets(
    sets: Sequence[dict[str, Any]], today: dt.date, count: int
) -> list[str]:
    """The `count` most recent draftable sets already released by `today`.

    `sets` is Scryfall's set list. A set announced for next month is listed
    there before it exists to draft, so anything not yet released is skipped.
    """
    released = [
        s
        for s in sets
        if s.get("set_type") in DRAFTABLE_SET_TYPES
        and s.get("released_at")
        and dt.date.fromisoformat(s["released_at"]) <= today
    ]
    released.sort(key=lambda s: (s["released_at"], s["code"]), reverse=True)
    return [s["code"] for s in released[:count]]


def bulk_entry(
    index: dict[str, Any], bulk_type: str = "default_cards"
) -> tuple[str, dt.datetime | None]:
    """The download URL and last-updated time of one bulk file.

    `default_cards` (every printing) rather than `oracle_cards` (one row per
    card): rarity and images belong to printings, and in Limited rarity is
    half the context.
    """
    for entry in index.get("data", []):
        if entry.get("type") != bulk_type:
            continue
        url = entry.get("jsonl_download_uri") or entry.get("download_uri")
        if not url:
            raise ValueError(f"bulk entry {bulk_type!r} has no download URI")
        updated = entry.get("updated_at")
        return url, dt.datetime.fromisoformat(updated) if updated else None
    raise ValueError(f"no bulk-data entry of type {bulk_type!r}")


def iter_cards(path: Path, set_codes: Collection[str]) -> Iterator[dict[str, Any]]:
    """Stream the gzipped JSONL bulk file, yielding the wanted sets' real cards.

    Reads the file it is handed and nothing else. Also tolerates the older
    single-JSON-array format, one card per line, in case Scryfall reverts.
    """
    wanted = {code.lower() for code in set_codes}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip().rstrip(",")
            if not line or line in ("[", "]"):
                continue
            card = json.loads(line)
            if str(card.get("set", "")).lower() not in wanted:
                continue
            if card.get("layout") in EXCLUDED_LAYOUTS or not card.get("oracle_id"):
                continue  # tokens, art cards, and meld pieces with no oracle identity
            yield card


def rows_for(
    raw_cards: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The `cards` and `card_prints` rows for a stream of Scryfall cards.

    `cards` is de-duplicated by oracle id: a set prints the same card several
    times (showcase, borderless, the basic lands), and Postgres refuses an
    upsert that touches the same row twice in one statement.
    """
    cards: dict[uuid.UUID, dict[str, Any]] = {}
    prints: list[dict[str, Any]] = []
    for raw in raw_cards:
        card, printing = parse_card(raw)
        cards[card["oracle_id"]] = card
        prints.append(printing)
    return list(cards.values()), prints


def should_skip(
    last_run: tuple[dt.datetime | None, str] | None,
    upstream_updated_at: dt.datetime | None,
    scope: str,
    *,
    force: bool = False,
) -> bool:
    """True when the last run already ingested this scope from this file.

    `last_run` is (its upstream_updated_at, its scope). If upstream gives no
    date, there is no way to know nothing changed, so the run goes ahead.
    """
    if force or last_run is None or upstream_updated_at is None:
        return False
    return last_run == (upstream_updated_at, scope)


def upsert(
    model: type[CardSet] | type[Card] | type[CardPrint], rows: list[dict[str, Any]]
) -> Insert:
    """INSERT ... ON CONFLICT DO UPDATE for one batch of rows.

    Every column except the primary key is overwritten, so a re-run picks up
    Scryfall's corrections (errata, new images) without duplicating anything.
    """
    statement = pg_insert(model).values(rows)
    keys = [column.name for column in model.__mapper__.primary_key]
    return statement.on_conflict_do_update(
        index_elements=keys,
        set_={name: statement.excluded[name] for name in rows[0] if name not in keys},
    )


def _batches(rows: list[dict[str, Any]]) -> Iterator[list[dict[str, Any]]]:
    for start in range(0, len(rows), BATCH_SIZE):
        yield rows[start : start + BATCH_SIZE]


# --------------------------------------------------------------------------
# The ingest (I/O)
# --------------------------------------------------------------------------


def _prune_older_bulk_files(keep: Path) -> None:
    """Delete earlier downloads of the same bulk file.

    Each Scryfall update has a new file name (it carries a timestamp), so
    without this every refresh would leave another 78 MB behind.
    """
    # "default-cards-20261014090455.jsonl.gz" -> "default-cards"
    prefix = re.sub(r"-\d+\..*$", "", keep.name)
    for old in keep.parent.glob(f"{prefix}-*"):
        if old != keep:
            old.unlink()


def load(
    session: Session,
    *,
    set_codes: Sequence[str] | None = None,
    recent: int = 3,
    force: bool = False,
    today: dt.date | None = None,
    report: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Run the Scryfall ingest. Returns a summary.

    With `set_codes`, exactly those sets; otherwise the `recent` most recent
    draftable sets. Skips the download and upserts entirely when the last run
    already ingested the same sets from the same bulk file, unless `force`.
    """
    all_sets = json.loads(fetch_json_bytes(SETS_URL))["data"]
    codes = sorted(
        code.lower()
        for code in (
            set_codes
            or recent_draftable_sets(
                all_sets, today or dt.datetime.now(dt.UTC).date(), recent
            )
        )
    )
    known = {s["code"]: s for s in all_sets}
    unknown = [code for code in codes if code not in known]
    if unknown:
        raise ValueError(f"Scryfall has no set with code {', '.join(unknown)}")
    scope = ",".join(codes)

    url, upstream_updated_at = bulk_entry(json.loads(fetch_json_bytes(BULK_INDEX_URL)))
    last = session.execute(
        select(IngestRun.upstream_updated_at, IngestRun.scope)
        .where(IngestRun.source == SOURCE)
        .order_by(IngestRun.ran_at.desc())
        .limit(1)
    ).first()
    last_run = (last[0], last[1]) if last else None
    if should_skip(last_run, upstream_updated_at, scope, force=force):
        report(
            f"[scryfall] {scope}: unchanged since the last run ({upstream_updated_at}); nothing to do"
        )
        return {"skipped": True, "sets": codes}

    report(f"[scryfall] sets: {scope}")
    path = fetch_to_file(
        url, settings.raw_data_dir / "scryfall" / url.rsplit("/", 1)[-1], force=force
    )
    _prune_older_bulk_files(path)
    report(f"[scryfall] reading {path.name}")
    cards, prints = rows_for(iter_cards(path, codes))

    # Sets first: card_prints.set_code is a foreign key to them.
    session.execute(upsert(CardSet, [parse_set(known[code]) for code in codes]))
    for batch in _batches(cards):
        session.execute(upsert(Card, batch))
    for batch in _batches(prints):
        session.execute(upsert(CardPrint, batch))
    session.add(
        IngestRun(
            source=SOURCE,
            source_url=url,
            upstream_updated_at=upstream_updated_at,
            scope=scope,
            row_count=len(prints),
            notes=f"{len(cards)} cards, {len(prints)} printings",
        )
    )
    session.commit()
    report(
        f"[scryfall] {len(cards)} cards, {len(prints)} printings across {len(codes)} sets"
    )
    return {"skipped": False, "sets": codes, "cards": len(cards), "prints": len(prints)}
