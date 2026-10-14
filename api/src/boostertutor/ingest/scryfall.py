"""Scryfall ingest: every card and printing in the recent draftable sets.

Development plan 2.2, ported from DraftDouble's `ingest/scryfall.py`, which
was proven against HOB. Two things about Scryfall's bulk data that differ
from what older docs (and the plan) describe, both confirmed in DraftDouble:

  * The bulk index advertises `jsonl_download_uri`: newline-delimited JSON,
    gzipped, about 78 MB. We stream it line by line, so no extra dependency
    (the plan suggested `ijson`) and never more than one card in memory.
  * `api.scryfall.com` rejects requests without an `Accept` header
    (see `fetching.py`).

Each set's bonus sheet comes along: the cards a set's packs can hold that
Scryfall files under another set (Special Guests, Marvel Universe). They are
the names in the set's 17Lands draft dump header that are not the set's own
cards; see `models/booster.py`.

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

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..config import settings
from ..models import BoosterCard, Card, CardPrint, CardSet, IngestRun
from .fetching import FetchError, fetch_gzip_first_line, fetch_json_bytes, fetch_to_file

# One definition of how cards are matched by name, shared with the 17Lands ingest.
from .seventeen_lands import draft_data_url, name_key, pack_card_names

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


def _bulk_lines(path: Path) -> Iterator[dict[str, Any]]:
    """Every real card in the gzipped JSONL bulk file, one at a time.

    Streaming matters: uncompressed, the file is well over a gigabyte. Also
    tolerates the older single-JSON-array format, one card per line, in case
    Scryfall reverts. Tokens, art cards, and meld pieces with no oracle
    identity are dropped here.
    """
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip().rstrip(",")
            if not line or line in ("[", "]"):
                continue
            card = json.loads(line)
            if card.get("layout") in EXCLUDED_LAYOUTS or not card.get("oracle_id"):
                continue
            yield card


def scan_bulk(
    cards: Iterable[dict[str, Any]], set_codes: Collection[str], names: Collection[str]
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """One pass over the bulk file, collecting two things.

    * Every printing in the wanted sets: their own cards.
    * Every printing, from any set, of a card named in `names` (name keys):
      the candidates a bonus-sheet card will be chosen from.
    """
    wanted_sets = {code.lower() for code in set_codes}
    wanted_names = set(names)
    own: list[dict[str, Any]] = []
    candidates: dict[str, list[dict[str, Any]]] = {}
    for card in cards:
        if str(card.get("set", "")).lower() in wanted_sets:
            own.append(card)
        key = name_key(card["name"])
        if key in wanted_names:
            candidates.setdefault(key, []).append(card)
    return own, candidates


def choose_bonus_printing(
    printings: Sequence[dict[str, Any]], set_types: dict[str, str]
) -> dict[str, Any]:
    """Which printing of a bonus-sheet card to store.

    A bonus sheet is a "masterpiece"-type set on Scryfall (Special Guests,
    Marvel Universe), so a printing from one of those is preferred; among
    equals, the most recent. The card's rules text is the same in every
    printing, so the choice only decides its rarity and image.
    """
    return max(
        printings,
        key=lambda raw: (
            set_types.get(str(raw.get("set")), "") == "masterpiece",
            str(raw.get("released_at") or ""),
            str(raw.get("collector_number") or ""),
        ),
    )


def booster_rows(
    set_code: str,
    own_oracle_ids: Iterable[uuid.UUID],
    bonus_oracle_ids: Iterable[uuid.UUID],
) -> list[dict[str, Any]]:
    """The `booster_cards` rows for one set. A card on both sheets counts as main."""
    rows = {oid: "main" for oid in own_oracle_ids}
    for oid in bonus_oracle_ids:
        rows.setdefault(oid, "bonus")
    return [
        {"set_code": set_code, "oracle_id": oid, "sheet": sheet}
        for oid, sheet in rows.items()
    ]


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
    model: type[CardSet] | type[Card] | type[CardPrint] | type[BoosterCard],
    rows: list[dict[str, Any]],
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


def _pack_names(code: str, report: Callable[[str], None]) -> list[str]:
    """The card names a set's 17Lands draft dump says were in its packs.

    Reads only the dump's first line. A set too new for 17Lands to have
    published a dump has none yet: its bonus sheet is then picked up on a
    later run, once the dump exists.
    """
    try:
        return pack_card_names(fetch_gzip_first_line(draft_data_url(code)))
    except FetchError as exc:
        report(
            f"[scryfall] {code}: no 17Lands draft dump yet, so no bonus sheet ({exc})"
        )
        return []


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
    draftable sets. Each set's bonus-sheet cards come along too (see
    `booster.py`). Skips everything when the last run already ingested the
    same sets from the same bulk file, unless `force`.
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
    pack_names = {
        code: {name_key(n) for n in _pack_names(code, report)} for code in codes
    }

    path = fetch_to_file(
        url, settings.raw_data_dir / "scryfall" / url.rsplit("/", 1)[-1], force=force
    )
    _prune_older_bulk_files(path)
    report(f"[scryfall] reading {path.name}")
    own, candidates = scan_bulk(
        _bulk_lines(path), codes, set().union(*pack_names.values())
    )

    # Bonus cards: names a set's packs held that are not that set's own cards.
    set_types = {s["code"]: s.get("set_type") or "" for s in all_sets}
    printings = list(own)
    boosters: list[dict[str, Any]] = []
    unresolved: list[str] = []
    bonus_total = 0
    for code in codes:
        mine = [raw for raw in own if raw["set"] == code]
        own_keys = {name_key(raw["name"]) for raw in mine}
        bonus = []
        for key in sorted(pack_names[code] - own_keys):
            if key not in candidates:
                unresolved.append(f"{code}:{key}")
                continue
            bonus.append(choose_bonus_printing(candidates[key], set_types))
        printings.extend(bonus)
        bonus_total += len(bonus)
        boosters += booster_rows(
            code,
            (uuid.UUID(raw["oracle_id"]) for raw in mine),
            (uuid.UUID(raw["oracle_id"]) for raw in bonus),
        )
        report(
            f"[scryfall] {code}: {len(own_keys)} own cards, {len(bonus)} bonus-sheet cards"
        )
    if unresolved:
        report(
            f"[scryfall] {len(unresolved)} pack names matched no Scryfall card: {unresolved[:10]}"
        )

    cards, prints = rows_for(printings)
    # The bonus printings' own sets (spg, mar) must exist too: card_prints
    # points at them. They are stored as the sets they are, not draftable.
    print_sets = sorted({p["set_code"] for p in prints} | set(codes))

    # Sets first, then cards, then printings and booster contents, which
    # point at both.
    session.execute(upsert(CardSet, [parse_set(known[code]) for code in print_sets]))
    for batch in _batches(cards):
        session.execute(upsert(Card, batch))
    for batch in _batches(prints):
        session.execute(upsert(CardPrint, batch))
    # Replace, not merge: a card that has left a set's packs must leave its list.
    session.execute(delete(BoosterCard).where(BoosterCard.set_code.in_(codes)))
    for batch in _batches(boosters):
        session.execute(upsert(BoosterCard, batch))
    session.add(
        IngestRun(
            source=SOURCE,
            source_url=url,
            upstream_updated_at=upstream_updated_at,
            scope=scope,
            row_count=len(prints),
            notes=(
                f"{len(cards)} cards, {len(prints)} printings, {bonus_total} bonus-sheet cards"
                + (f"; unresolved: {', '.join(unresolved)}" if unresolved else "")
            ),
        )
    )
    session.commit()
    report(
        f"[scryfall] {len(cards)} cards, {len(prints)} printings across {len(codes)} sets"
    )
    return {
        "skipped": False,
        "sets": codes,
        "cards": len(cards),
        "prints": len(prints),
        "bonus": bonus_total,
        "unresolved": unresolved,
    }
