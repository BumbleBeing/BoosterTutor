"""17Lands ingest: card and archetype win rates from the public datasets.

Development plan 2.3, ported from DraftDouble's `ingest/seventeen_lands.py`,
which was checked against HOB. See `docs/decisions/0002-17lands-data-access.md`
for why only the public datasets are used (17Lands asks that the endpoints
behind its own website not be used elsewhere), so every number here is
computed by us rather than read from 17Lands.

Two dumps per set and format:

  * `draft_data_public.{SET}.{FORMAT}.csv.gz`, one row per pick, gives
    ALSA and ATA.
  * `game_data_public.{SET}.{FORMAT}.csv.gz`, one row per game, gives every
    win rate. It has a column per card per zone (opening hand, drawn,
    tutored, deck, sideboard), which is why it runs to 1,000+ columns.

Run it with:

    uv run python -m boostertutor.ingest 17lands              # every ingested draftable set
    uv run python -m boostertutor.ingest 17lands --sets hob   # exactly these

Data from 17Lands (https://www.17lands.com/public_datasets), CC BY 4.0. The
etiquette in CLAUDE.md applies: cached snapshots only, at most one request
per set and format per day, never from a user request path. Everything above
`load` is pure and tested directly.
"""

import csv
import datetime as dt
import gzip
import re
import sys
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    ArchetypeStats,
    BoosterCard,
    Card,
    CardArchetypeStats,
    CardDraftStats,
    CardSet,
    IngestRun,
)
from ..parsing.names import name_key
from .fetching import UpstreamMissing, fetch_last_modified, fetch_to_file
from .runs import RunRecord, recorded_run

S3_BASE = "https://17lands-public.s3.amazonaws.com/analysis_data"
SOURCE = "17lands"
DEFAULT_EVENT_TYPE = "PremierDraft"

# Every card that appears in a pack has a `pack_card_<name>` column.
PACK_CARD_PREFIX = "pack_card_"

# The zones a card can be in during a game, as game-data column prefixes.
OPENING_HAND = "opening_hand_"
DRAWN = ("drawn_", "tutored_")
DECK = "deck_"

# Cell values that mean "not there". Testing membership on the raw string is
# far cheaper than parsing a number: these cells are read hundreds of
# millions of times in one run, and int(float(x)) was the single biggest cost
# in DraftDouble's ingest before this.
ABSENT = frozenset({"0", "", "0.0", "False", "false"})

# Rows per INSERT; Postgres caps a statement at 65,535 bound parameters.
BATCH_SIZE = 1000

# The game files are ~1,000 columns wide, past the csv module's default limit.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def draft_data_url(set_code: str, event_type: str = DEFAULT_EVENT_TYPE) -> str:
    """17Lands spells set codes in upper case: `HOB`, not `hob`."""
    return (
        f"{S3_BASE}/draft_data/draft_data_public.{set_code.upper()}.{event_type}.csv.gz"
    )


def game_data_url(set_code: str, event_type: str = DEFAULT_EVENT_TYPE) -> str:
    return (
        f"{S3_BASE}/game_data/game_data_public.{set_code.upper()}.{event_type}.csv.gz"
    )


def pack_card_names(header_line: str) -> list[str]:
    """Every card name a draft dump's header says appeared in a pack.

    A double-faced card is named by its front face alone, as 17Lands does.
    """
    header = next(csv.reader([header_line]))
    return [
        column[len(PACK_CARD_PREFIX) :]
        for column in header
        if column.startswith(PACK_CARD_PREFIX)
    ]


# --------------------------------------------------------------------------
# Small helpers (pure)
# --------------------------------------------------------------------------


def sorted_pair(colors: str) -> str | None:
    """A 17Lands `main_colors` value as a sorted WUBRG pair, or None.

    Mono-colour and three-or-more-colour decks are real, but they are not one
    of the ten archetypes, so they count only towards the overall rates.
    """
    letters = {c for c in colors.strip() if c in "WUBRG"}
    if len(letters) != 2:
        return None
    return "".join(c for c in "WUBRG" if c in letters)


def _int(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _won(value: str) -> bool:
    return value.strip().lower() in ("true", "1")


def _card_columns(
    header: Sequence[str], prefixes: Sequence[str]
) -> dict[str, dict[str, int]]:
    """card name -> {zone prefix: column index}, built once per file.

    Doing this up front keeps the row loop to integer indexing.
    """
    columns: dict[str, dict[str, int]] = defaultdict(dict)
    for index, name in enumerate(header):
        for prefix in prefixes:
            if name.startswith(prefix):
                columns[name[len(prefix) :]][prefix] = index
                break
    return dict(columns)


# --------------------------------------------------------------------------
# The draft dump -> ALSA and ATA (pure)
# --------------------------------------------------------------------------


def aggregate_draft_data(
    rows: Iterable[Sequence[str]],
    header: Sequence[str],
    progress: Callable[[int], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """card name -> {alsa, ata, seen_count, pick_count}.

    ALSA (average last seen at): over every (draft, pack number) in which the
    card appeared, the latest pick at which it was still in a pack the drafter
    was handed, averaged. ATA (average taken at): the mean pick at which it was
    taken. Both 1-based: the dumps are 0-indexed, and without the +1 every
    ALSA and ATA comes out exactly one pick low -- a plausible-looking wrong
    answer rather than an obvious crash.

    Rows must arrive grouped by draft, as 17Lands writes them: state is kept
    for one draft at a time, so memory stays flat.
    """
    index = {name: i for i, name in enumerate(header)}
    pack_items = [
        (columns[PACK_CARD_PREFIX], card)
        for card, columns in _card_columns(header, [PACK_CARD_PREFIX]).items()
        if PACK_CARD_PREFIX in columns
    ]
    seen_total: dict[str, int] = defaultdict(int)
    seen_count: dict[str, int] = defaultdict(int)
    taken_total: dict[str, int] = defaultdict(int)
    taken_count: dict[str, int] = defaultdict(int)

    current_draft: str | None = None
    last_seen: dict[tuple[str, str], int] = {}

    def flush() -> None:
        for (_pack, card), pick in last_seen.items():
            seen_total[card] += pick
            seen_count[card] += 1
        last_seen.clear()

    draft_col, pack_col, pick_col, taken_col = (
        index["draft_id"],
        index["pack_number"],
        index["pick_number"],
        index["pick"],
    )
    for processed, row in enumerate(rows, start=1):
        if progress is not None and processed % 250_000 == 0:
            progress(processed)
        if row[draft_col] != current_draft:
            flush()
            current_draft = row[draft_col]
        pack = row[pack_col]
        pick = _int(row[pick_col]) + 1
        if taken := row[taken_col].strip():
            taken_total[taken] += pick
            taken_count[taken] += 1
        for column, card in pack_items:
            if row[column] not in ABSENT and pick > last_seen.get((pack, card), 0):
                last_seen[(pack, card)] = pick
    flush()

    return {
        card: {
            "alsa": seen_total[card] / seen_count[card] if seen_count[card] else None,
            "ata": taken_total[card] / taken_count[card] if taken_count[card] else None,
            "seen_count": seen_count[card],
            "pick_count": taken_count[card],
        }
        for card in set(seen_count) | set(taken_count)
    }


# --------------------------------------------------------------------------
# The game dump -> win rates (pure)
# --------------------------------------------------------------------------

# The five game counts kept per card: in the deck (GP), in the opening hand
# (OH), drawn after the opening hand (GD), in hand at some point (GIH = OH or
# GD), and in the deck but never in hand (GND).
OUTCOMES = ("gp", "oh", "gd", "gih", "gnd")


def _new_counts() -> dict[str, int]:
    return {f"{o}_{k}": 0 for o in OUTCOMES for k in ("games", "wins")}


def aggregate_game_data(
    rows: Iterable[Sequence[str]],
    header: Sequence[str],
    progress: Callable[[int], None] | None = None,
) -> tuple[
    dict[str, dict[str, int]],
    dict[tuple[str, str], dict[str, int]],
    dict[str, dict[str, int]],
]:
    """Count games and wins per card, overall and per archetype.

    Returns (overall, by_archetype, archetypes):
      overall       card name -> the five game/win counts
      by_archetype  (card name, pair) -> the same, in that archetype's decks only
      archetypes    pair -> {wins, games}, the archetype's own record

    A game counts once per card per outcome, however many copies were drawn.
    OH and GD split GIH: a card in the opening hand counts as OH even if
    another copy was drawn later.
    """
    index = {name: i for i, name in enumerate(header)}
    prefixes = [OPENING_HAND, *DRAWN, DECK]
    card_items = [
        (
            columns[DECK],
            columns.get(OPENING_HAND),
            tuple(columns[p] for p in DRAWN if p in columns),
            card,
        )
        for card, columns in _card_columns(header, prefixes).items()
        if DECK in columns
    ]
    overall: dict[str, dict[str, int]] = defaultdict(_new_counts)
    by_archetype: dict[tuple[str, str], dict[str, int]] = defaultdict(_new_counts)
    archetypes: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "games": 0})

    won_col, colors_col = index["won"], index["main_colors"]
    for processed, row in enumerate(rows, start=1):
        if progress is not None and processed % 50_000 == 0:
            progress(processed)
        won = int(_won(row[won_col]))
        pair = sorted_pair(row[colors_col])
        if pair:
            archetypes[pair]["games"] += 1
            archetypes[pair]["wins"] += won

        for deck_col, hand_col, drawn_cols, card in card_items:
            if row[deck_col] in ABSENT:
                continue
            in_hand = hand_col is not None and row[hand_col] not in ABSENT
            drawn = any(row[c] not in ABSENT for c in drawn_cols)
            outcomes = ["gp"]
            if in_hand:
                outcomes += ["oh", "gih"]
            elif drawn:
                outcomes += ["gd", "gih"]
            else:
                outcomes.append("gnd")
            targets = [overall[card]]
            if pair:
                targets.append(by_archetype[(card, pair)])
            for counts in targets:
                for outcome in outcomes:
                    counts[f"{outcome}_games"] += 1
                    counts[f"{outcome}_wins"] += won

    return dict(overall), dict(by_archetype), dict(archetypes)


def rate(wins: int, games: int) -> float | None:
    """A win rate in percentage points, the unit the fitness function uses."""
    return 100.0 * wins / games if games else None


def card_rates(counts: dict[str, int]) -> dict[str, Any]:
    """The stored rate columns for one card's counts, IWD included."""
    out: dict[str, Any] = {}
    for outcome in OUTCOMES:
        out[f"{outcome}_wr"] = rate(
            counts[f"{outcome}_wins"], counts[f"{outcome}_games"]
        )
        out[f"{outcome}_games"] = counts[f"{outcome}_games"]
    gih, gnd = out["gih_wr"], out["gnd_wr"]
    out["iwd"] = gih - gnd if gih is not None and gnd is not None else None
    return out


def build_rows(
    set_code: str,
    event_type: str,
    snapshot: dt.date,
    resolve: dict[str, uuid.UUID],
    draft_stats: dict[str, dict[str, Any]],
    overall: dict[str, dict[str, int]],
    by_archetype: dict[tuple[str, str], dict[str, int]],
    archetypes: dict[str, dict[str, int]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """The rows for all three tables, and the names that matched no card.

    `resolve` maps name keys (see `name_key`) to oracle ids: the cards the
    set's packs can hold, bonus sheet included.
    """
    key = {"set_code": set_code, "event_type": event_type, "snapshot_date": snapshot}
    unmatched = sorted(
        n for n in set(draft_stats) | set(overall) if name_key(n) not in resolve
    )

    card_rows = []
    for name in sorted(set(draft_stats) | set(overall)):
        if (oid := resolve.get(name_key(name))) is None:
            continue
        drafted = draft_stats.get(name, {})
        card_rows.append(
            {
                **key,
                "oracle_id": oid,
                "seen_count": drafted.get("seen_count", 0),
                "alsa": drafted.get("alsa"),
                "pick_count": drafted.get("pick_count", 0),
                "ata": drafted.get("ata"),
                **card_rates(overall.get(name, _new_counts())),
            }
        )
    archetype_card_rows = [
        {
            **key,
            "oracle_id": resolve[name_key(name)],
            "archetype": pair,
            **card_rates(counts),
        }
        for (name, pair), counts in sorted(by_archetype.items())
        if name_key(name) in resolve
    ]
    archetype_rows = [
        {
            **key,
            "archetype": pair,
            "wins": t["wins"],
            "games": t["games"],
            "win_rate": rate(t["wins"], t["games"]),
        }
        for pair, t in sorted(archetypes.items())
    ]
    return card_rows, archetype_card_rows, archetype_rows, unmatched


def should_skip(
    last_upstream: dt.datetime | None,
    upstream: dt.datetime | None,
    *,
    force: bool = False,
) -> bool:
    """True when this set and format were last ingested from this same dump."""
    if force or last_upstream is None or upstream is None:
        return False
    return last_upstream == upstream


# --------------------------------------------------------------------------
# The ingest (I/O)
# --------------------------------------------------------------------------


@contextmanager
def _csv_rows(path: Path) -> Iterator[tuple[list[str], Iterator[list[str]]]]:
    """(header, the remaining rows) of a gzipped CSV, closed when done."""
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        yield next(reader), reader


def _download(url: str, stamp: dt.date) -> Path:
    """Fetch a dump into data/raw/17lands/, named for its upstream date.

    The date in the name means a newer dump is a new file rather than a
    stale cache hit, and older copies of the same dump are removed.
    """
    base = url.rsplit("/", 1)[-1].removesuffix(".csv.gz")
    dest = settings.raw_data_dir / "17lands" / f"{base}.{stamp:%Y%m%d}.csv.gz"
    path = fetch_to_file(url, dest)
    for old in dest.parent.glob(f"{base}.*.csv.gz"):
        if old != dest and re.fullmatch(
            rf"{re.escape(base)}\.\d{{8}}\.csv\.gz", old.name
        ):
            old.unlink()
    return path


def _insert(session: Session, model: Any, rows: list[dict[str, Any]]) -> None:
    for start in range(0, len(rows), BATCH_SIZE):
        session.execute(insert(model), rows[start : start + BATCH_SIZE])


def default_sets(session: Session) -> list[str]:
    """Every draftable set whose pack contents the Scryfall ingest has loaded."""
    query = (
        select(CardSet.set_code)
        .join(BoosterCard, BoosterCard.set_code == CardSet.set_code)
        .where(CardSet.is_draftable)
        .distinct()
        .order_by(CardSet.set_code)
    )
    return list(session.scalars(query))


def load_set(
    session: Session,
    set_code: str,
    *,
    event_type: str = DEFAULT_EVENT_TYPE,
    force: bool = False,
    report: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Ingest one set and format, recorded in `ingest_runs`. Returns a summary."""
    with recorded_run(session, SOURCE, f"{set_code}:{event_type}") as record:
        return _load_set(session, record, set_code, event_type, force, report)


def _load_set(
    session: Session,
    record: RunRecord,
    set_code: str,
    event_type: str,
    force: bool,
    report: Callable[[str], None],
) -> dict[str, Any]:
    tag = f"[17lands] {set_code} {event_type}"
    scope = record.scope
    game_url, draft_url = (
        game_data_url(set_code, event_type),
        draft_data_url(set_code, event_type),
    )
    record.source_url = f"{draft_url} + {game_url}"
    try:
        upstream = fetch_last_modified(game_url)
    except UpstreamMissing as exc:
        # Not a failure: 17Lands has not published this set's game dump yet.
        report(f"{tag}: no public dataset yet ({exc})")
        record.status, record.notes = "skipped", "no public game dump yet"
        return {"set": set_code, "skipped": True, "reason": "no dataset"}
    record.upstream_updated_at = upstream

    last = session.scalar(
        select(IngestRun.upstream_updated_at)
        .where(
            IngestRun.source == SOURCE,
            IngestRun.scope == scope,
            IngestRun.status == "succeeded",
        )
        .order_by(IngestRun.started_at.desc())
        .limit(1)
    )
    if should_skip(last, upstream, force=force):
        report(f"{tag}: unchanged since the last run ({upstream}); nothing to do")
        record.status = "skipped"
        return {"set": set_code, "skipped": True, "reason": "unchanged"}

    snapshot = (upstream or dt.datetime.now(dt.UTC)).astimezone(dt.UTC).date()
    resolve = {
        name_key(name): oid
        for name, oid in session.execute(
            select(Card.name, BoosterCard.oracle_id)
            .join(Card, Card.oracle_id == BoosterCard.oracle_id)
            .where(BoosterCard.set_code == set_code)
        )
    }
    if not resolve:
        raise RuntimeError(
            f"{set_code} has no pack contents yet: run the Scryfall ingest first"
        )

    draft_path = _download(draft_url, snapshot)
    report(f"{tag}: reading {draft_path.name} for ALSA and ATA")
    with _csv_rows(draft_path) as (header, reader):
        draft_stats = aggregate_draft_data(
            reader, header, lambda n: report(f"{tag}:   {n:,} picks")
        )

    game_path = _download(game_url, snapshot)
    report(f"{tag}: reading {game_path.name} for win rates")
    with _csv_rows(game_path) as (header, reader):
        overall, by_archetype, archetypes = aggregate_game_data(
            reader, header, lambda n: report(f"{tag}:   {n:,} games")
        )

    cards, archetype_cards, archetype_rows, unmatched = build_rows(
        set_code,
        event_type,
        snapshot,
        resolve,
        draft_stats,
        overall,
        by_archetype,
        archetypes,
    )
    # Replace this snapshot if it was ingested before (a --force re-run).
    for model in (CardDraftStats, CardArchetypeStats, ArchetypeStats):
        session.execute(
            delete(model).where(
                model.set_code == set_code,
                model.event_type == event_type,
                model.snapshot_date == snapshot,
            )
        )
    _insert(session, CardDraftStats, cards)
    _insert(session, CardArchetypeStats, archetype_cards)
    _insert(session, ArchetypeStats, archetype_rows)
    record.row_count = len(cards) + len(archetype_cards) + len(archetype_rows)
    record.notes = (
        f"snapshot {snapshot}: {len(cards)} cards, {len(archetype_cards)} card-archetype rows, "
        f"{len(archetype_rows)} archetypes; {len(unmatched)} names unmatched"
        + (f": {', '.join(unmatched[:10])}" if unmatched else "")
    )
    # recorded_run commits the data and this run's row together.
    report(
        f"{tag}: snapshot {snapshot}: {len(cards)} cards, {len(archetype_cards)} card-archetype rows, "
        f"{len(archetype_rows)} archetypes, {len(unmatched)} names unmatched"
    )
    return {
        "set": set_code,
        "skipped": False,
        "snapshot": snapshot,
        "cards": len(cards),
        "unmatched": unmatched,
    }


def load(
    session: Session,
    *,
    set_codes: Sequence[str] | None = None,
    event_type: str = DEFAULT_EVENT_TYPE,
    force: bool = False,
    report: Callable[[str], None] = print,
) -> list[dict[str, Any]]:
    """Ingest each set in turn.

    One set failing does not stop the others: its failure is already
    recorded in `ingest_runs`, and the rest still get their chance. The run
    as a whole then raises, so the nightly Action is marked failed.
    """
    codes = [c.lower() for c in set_codes] if set_codes else default_sets(session)
    results, failed = [], []
    for code in codes:
        try:
            results.append(
                load_set(
                    session, code, event_type=event_type, force=force, report=report
                )
            )
        except Exception as exc:  # noqa: BLE001 -- recorded by load_set, reported here, raised below
            report(f"[17lands] {code} {event_type}: FAILED: {exc}")
            failed.append(code)
    if failed:
        raise RuntimeError(
            f"17Lands ingest failed for {', '.join(failed)}; see ingest_runs"
        )
    return results
