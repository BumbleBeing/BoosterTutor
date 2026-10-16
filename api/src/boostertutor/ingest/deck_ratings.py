"""Fit each format's Deck Ratings from the 17Lands game dump (ADR 0026 s2).

    uv run python -m boostertutor.ingest deck-ratings [--sets hob] [--event-type PremierDraft]

Every row of the game dump is one game, with a `deck_<card>` column per card
holding how many copies the deck ran, basic lands included, beside whether
the game was won. This reads each distinct 40-card deck once (a deck is a
draft and a `build_index`), scores it with the same `deck_metrics` a
Submitted Deck gets, and fits the percentile tables and the regression from
the result. The fit replaces any stored for the same format and dump.

Reads the dump the 17Lands ingest cached under `data/raw/17lands/`, and
never calls 17Lands itself. Run it after `taxonomy`, since the synergy,
removal, mana and land metrics read the set's tags and Fixers.
"""

import csv
import datetime as dt
import gzip
import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from ..analysis.deck import deck_metrics
from ..analysis.deck_rating import ScoredDeck, fit_model, metric_values
from ..format_inputs import FormatNotReady, load_format_inputs, name_index
from ..models import DeckRatingModelRow
from ..parsing.names import name_key
from ..schemas.deck import DECK_SIZE, Deck
from .runs import recorded_run
from .seventeen_lands import DEFAULT_EVENT_TYPE
from .synergy_baseline import cached_dump

SOURCE = "deck_ratings"

# The game dump names basics by their card names.
BASIC_COLOURS = {
    "Plains": "W",
    "Island": "U",
    "Swamp": "B",
    "Mountain": "R",
    "Forest": "G",
}
DECK, SIDEBOARD = "deck_", "sideboard_"


@dataclass
class DumpDeck:
    """One distinct deck from the dump, and how its games went."""

    deck: Deck
    wins: int = 0
    games: int = 0


@dataclass
class DumpDecks:
    """The dump's usable decks, and how many distinct decks were left out."""

    decks: list[DumpDeck] = field(default_factory=list)
    not_40: int = 0  # 17Lands records larger decks; the Submitted Deck is 40
    unknown_cards: int = 0  # holding a card `names` does not know


def decks_from_game_rows(
    header: Sequence[str], rows: Iterable[Sequence[str]], names: Mapping[str, uuid.UUID]
) -> DumpDecks:
    """Each distinct 40-card deck, in the order first seen, with its record.

    Pure. Basics in the sideboard are dropped, as the deck builder prunes
    them from the pool (ADR 0025 s1).
    """
    idx = {name: i for i, name in enumerate(header)}
    main_cols: list[tuple[int, uuid.UUID | None]] = []
    basic_cols: list[tuple[int, str]] = []
    side_cols: list[tuple[int, uuid.UUID]] = []
    for name, i in idx.items():
        if name.startswith(DECK):
            card = name.removeprefix(DECK)
            if card in BASIC_COLOURS:
                basic_cols.append((i, BASIC_COLOURS[card]))
            else:
                main_cols.append((i, names.get(name_key(card))))
        elif name.startswith(SIDEBOARD):
            oracle_id = names.get(name_key(name.removeprefix(SIDEBOARD)))
            if oracle_id is not None:
                side_cols.append((i, oracle_id))

    found = DumpDecks()
    seen: dict[tuple[str, str], DumpDeck | None] = {}
    draft_col, build_col, won_col = idx["draft_id"], idx["build_index"], idx["won"]
    for row in rows:
        key = (row[draft_col], row[build_col])
        if key not in seen:
            new = _deck(row, main_cols, basic_cols, side_cols, found)
            if new is not None:
                found.decks.append(new)
            seen[key] = new
        dump_deck = seen[key]
        if dump_deck is not None:
            dump_deck.games += 1
            dump_deck.wins += row[won_col].strip().lower() in ("true", "1")
    return found


def _deck(
    row: Sequence[str],
    main_cols: list[tuple[int, uuid.UUID | None]],
    basic_cols: list[tuple[int, str]],
    side_cols: list[tuple[int, uuid.UUID]],
    found: DumpDecks,
) -> DumpDeck | None:
    main: list[uuid.UUID] = []
    unknown = 0  # copies of cards `names` does not know
    for i, oracle_id in main_cols:
        copies = _count(row[i])
        if oracle_id is None:
            unknown += copies
        else:
            main += [oracle_id] * copies
    basics = {colour: _count(row[i]) for i, colour in basic_cols if _count(row[i])}
    if len(main) + unknown + sum(basics.values()) != DECK_SIZE:
        found.not_40 += 1
        return None
    if unknown:
        found.unknown_cards += 1
        return None
    sideboard = [oid for i, oid in side_cols for _ in range(_count(row[i]))]
    return DumpDeck(Deck(main=main, basics=basics, sideboard=sideboard))


def _count(cell: str) -> int:
    try:
        return int(float(cell))
    except ValueError:
        return 0


def snapshot_of(path_name: str) -> dt.date:
    """The date stamp the 17Lands ingest put in a cached dump's file name."""
    match = re.search(r"\.(\d{8})\.csv\.gz$", path_name)
    if match is None:
        raise ValueError(f"{path_name} has no date stamp")
    return dt.date.fromisoformat(match.group(1))  # "20261001" is ISO basic format


def load(
    session: Session, set_codes: list[str], event_type: str = DEFAULT_EVENT_TYPE
) -> None:
    for set_code in set_codes:
        with recorded_run(session, SOURCE, scope=f"{set_code}/{event_type}") as record:
            try:
                inputs = load_format_inputs(session, set_code, event_type)
                path = cached_dump("game_data_public", set_code, event_type)
            except (FormatNotReady, FileNotFoundError) as exc:
                print(f"{set_code}/{event_type}: skipped, {exc}")
                record.status, record.notes = "skipped", str(exc)
                continue
            record.source_url = path.name
            names = name_index(session, set_code)
            with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle)
                found = decks_from_game_rows(next(reader), reader, names)

            scored = [
                ScoredDeck(
                    metric_values(deck_metrics(d.deck, inputs)),
                    wins=d.wins,
                    games=d.games,
                )
                for d in found.decks
            ]
            model = fit_model(scored)
            snapshot = snapshot_of(path.name)
            session.execute(
                delete(DeckRatingModelRow).where(
                    DeckRatingModelRow.set_code == set_code,
                    DeckRatingModelRow.event_type == event_type,
                    DeckRatingModelRow.snapshot_date == snapshot,
                )
            )
            left_out = (
                f"{found.not_40:,} not of 40 cards and "
                f"{found.unknown_cards:,} with unknown cards left out"
            )
            if model is None:
                record.status = "skipped"
                record.notes = f"only {len(scored):,} decks, too few to fit; {left_out}"
                print(f"{set_code}/{event_type}: {record.notes}")
                continue
            session.execute(
                insert(DeckRatingModelRow),
                [
                    {
                        "set_code": set_code,
                        "event_type": event_type,
                        "snapshot_date": snapshot,
                        "decks": model.decks,
                        "games": model.games,
                        "intercept": model.intercept,
                        "coefficients": model.coefficients,
                        "standard_errors": model.standard_errors,
                        "quantiles": model.quantiles,
                        "source": path.name,
                    }
                ],
            )
            record.row_count = 1
            record.notes = f"{model.decks:,} decks, {model.games:,} games; {left_out}"
            print(f"{set_code}/{event_type}: {record.notes}")
            for metric, coef in model.coefficients.items():
                print(
                    f"  {metric:>16}: {coef:+.4f} (se {model.standard_errors[metric]:.4f})"
                )
