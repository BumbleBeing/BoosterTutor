"""The collaborators the draft endpoints need, gathered in one place.

The routes take a `DraftServices` instead of reaching for the database and
the network themselves. In production it is built over a Postgres session;
tests build one from a dict, saved payloads and the HOB statistics snapshot,
so the whole import path runs with no network and no database.
"""

import uuid
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Annotated, Any, Protocol

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .analysis.deck_rating import DeckRatingModel
from .analysis.draft import FormatInputs
from .config import settings
from .db import SessionLocal
from .drafts import fetch_seventeen_lands_draft, name_index
from .format_inputs import load_deck_rating_model, load_format_inputs
from .models import Card, CardPrint, Draft
from .rate_limit import FetchLimiter, FetchLimits, SqlLedger
from .schemas import DraftLog
from .schemas.draft_review import CardInfo

__all__ = ["CardInfo", "DraftServices", "get_services"]


class ReplayStore(Protocol):
    """The Replay Cache: parsed logs by 17Lands draft id."""

    def get(self, draft_id: str) -> DraftLog | None: ...
    def has(self, draft_id: str) -> bool: ...
    def add(self, log: DraftLog) -> None: ...


@dataclass
class DraftServices:
    store: ReplayStore
    limiter: FetchLimiter
    # Deck submissions have their own allowance (ADR 0031 s6). It is a
    # FetchLimiter over the same table, under a different key prefix.
    deck_limiter: FetchLimiter
    # (set code, event type) -> the fitted Deck Ratings, or None if unfitted.
    deck_model_for: Callable[[str, str], DeckRatingModel | None]
    # set code -> name_key -> oracle id, for matching a draft's card names.
    names_for: Callable[[str], dict[str, uuid.UUID]]
    # (set code, event type) -> the statistics a verdict is computed from.
    inputs_for: Callable[[str, str], FormatInputs]
    card_infos_for: Callable[[str, Iterable[uuid.UUID]], dict[uuid.UUID, CardInfo]]
    # set code -> the set's own basic lands by colour letter, for the deck
    # builder's tiles. A colour with no printing is simply absent.
    basic_lands_for: Callable[[str], dict[str, CardInfo]]
    # draft id -> (draft payload, event metadata): the one 17lands.com request.
    fetch: Callable[[str], tuple[dict[str, Any], dict[str, Any]]]
    supported_sets: frozenset[str]


class SqlReplayStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, draft_id: str) -> DraftLog | None:
        row = self.session.get(Draft, draft_id)
        return DraftLog.model_validate(row.log) if row else None

    def has(self, draft_id: str) -> bool:
        return self.session.get(Draft, draft_id) is not None

    def add(self, log: DraftLog) -> None:
        # Two people may submit the same new draft at once; the second insert
        # is simply ignored, since both hold the same log.
        self.session.execute(
            insert(Draft)
            .values(
                draft_id=log.source_id,
                set_code=log.set_code,
                log=log.model_dump(mode="json"),
            )
            .on_conflict_do_nothing(index_elements=["draft_id"])
        )
        self.session.commit()


def load_card_infos(
    session: Session, set_code: str, ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, CardInfo]:
    wanted = set(ids)
    cards = {
        c.oracle_id: c
        for c in session.scalars(select(Card).where(Card.oracle_id.in_(wanted)))
    }
    # A card can have several printings in a set (showcase, borderless); the
    # lowest collector number is the plain one. Sorted as text: good enough.
    prints: dict[uuid.UUID, CardPrint] = {}
    for p in session.scalars(
        select(CardPrint)
        .where(CardPrint.set_code == set_code, CardPrint.oracle_id.in_(wanted))
        .order_by(CardPrint.collector_number)
    ):
        prints.setdefault(p.oracle_id, p)
    return {
        oid: CardInfo(
            name=card.name,
            mana_cost=card.mana_cost,
            type_line=card.type_line,
            cmc=card.cmc,
            colors=card.colors,
            rarity=prints[oid].rarity if oid in prints else None,
            image_normal=prints[oid].image_normal if oid in prints else None,
            image_art_crop=prints[oid].image_art_crop if oid in prints else None,
        )
        for oid, card in cards.items()
    }


# The five basic lands by name, and the colour each one is added as.
BASIC_COLOURS = {
    "Plains": "W",
    "Island": "U",
    "Swamp": "B",
    "Mountain": "R",
    "Forest": "G",
}


def load_basic_lands(session: Session, set_code: str) -> dict[str, CardInfo]:
    """The set's own printing of each basic land, keyed by colour letter.

    The Scryfall ingest keeps every printing a set has, basics included. A set
    may print several art variants of each; the lowest collector number (as
    text, like `load_card_infos`) is the plain one.
    """
    rows = session.execute(
        select(Card, CardPrint)
        .join(CardPrint, CardPrint.oracle_id == Card.oracle_id)
        .where(CardPrint.set_code == set_code, Card.name.in_(BASIC_COLOURS))
        .order_by(CardPrint.collector_number)
    )
    out: dict[str, CardInfo] = {}
    for card, printing in rows:
        out.setdefault(
            BASIC_COLOURS[card.name],
            CardInfo(
                name=card.name,
                mana_cost=card.mana_cost,
                type_line=card.type_line,
                cmc=card.cmc,
                colors=card.colors,
                rarity=printing.rarity,
                image_normal=printing.image_normal,
                image_art_crop=printing.image_art_crop,
            ),
        )
    return out


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def get_services(session: Annotated[Session, Depends(get_session)]) -> DraftServices:
    return DraftServices(
        store=SqlReplayStore(session),
        limiter=FetchLimiter(
            SqlLedger(session),
            FetchLimits(
                per_minute=settings.fetch_limit_per_minute,
                per_day=settings.fetch_limit_per_day,
            ),
        ),
        deck_limiter=FetchLimiter(
            SqlLedger(session),
            FetchLimits(
                per_minute=settings.deck_limit_per_minute,
                per_day=settings.deck_limit_per_day,
            ),
        ),
        deck_model_for=lambda set_code, event_type: load_deck_rating_model(
            session, set_code, event_type
        ),
        names_for=lambda set_code: name_index(session, set_code),
        inputs_for=lambda set_code, event_type: load_format_inputs(
            session, set_code, event_type
        ),
        card_infos_for=lambda set_code, ids: load_card_infos(session, set_code, ids),
        basic_lands_for=lambda set_code: load_basic_lands(session, set_code),
        fetch=fetch_seventeen_lands_draft,
        supported_sets=settings.supported_set_codes,
    )
