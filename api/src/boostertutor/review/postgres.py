"""The real `ReviewService`, built over a Postgres session.

Each request gets its own session and its own service (`get_review_service`
is a FastAPI dependency). Tests replace that dependency with a service built
from in-memory fakes (`tests/review_world.py`).
"""

import uuid
from collections.abc import Iterable, Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..analysis.deck_rating import DeckRatingModel
from ..analysis.draft import FormatInputs
from ..config import settings
from ..db import SessionLocal
from ..format_inputs import load_deck_rating_model, load_format_inputs, name_index
from ..models import Card, CardPrint, Draft
from ..schemas import DraftLog
from ..schemas.draft_review import CardInfo
from .fetch import fetch_seventeen_lands_draft
from .rate_limit import Limits, RateLimiter, SqlLedger
from .service import ReviewService

# The five basic lands by name, and the colour each one is added as.
BASIC_COLOURS = {
    "Plains": "W",
    "Island": "U",
    "Swamp": "B",
    "Mountain": "R",
    "Forest": "G",
}


class SqlReplayStore:
    """The Replay Cache over the `drafts` table."""

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


class SqlCatalog:
    """The `Catalog` over the card, statistics and Deck Ratings tables."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def names(self, set_code: str) -> dict[str, uuid.UUID]:
        return name_index(self.session, set_code)

    def format_inputs(self, set_code: str, event_type: str) -> FormatInputs:
        return load_format_inputs(self.session, set_code, event_type)

    def deck_model(self, set_code: str, event_type: str) -> DeckRatingModel | None:
        return load_deck_rating_model(self.session, set_code, event_type)

    def card_infos(
        self, set_code: str, ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, CardInfo]:
        wanted = set(ids)
        # A card can have several printings in a set (showcase, borderless);
        # the lowest collector number is the plain one. Sorted as text, which
        # is good enough for telling the plain one apart.
        prints: dict[uuid.UUID, CardPrint] = {}
        for p in self.session.scalars(
            select(CardPrint)
            .where(CardPrint.set_code == set_code, CardPrint.oracle_id.in_(wanted))
            .order_by(CardPrint.collector_number)
        ):
            prints.setdefault(p.oracle_id, p)
        cards = self.session.scalars(select(Card).where(Card.oracle_id.in_(wanted)))
        return {c.oracle_id: _card_info(c, prints.get(c.oracle_id)) for c in cards}

    def basic_lands(self, set_code: str) -> dict[str, CardInfo]:
        """The Scryfall ingest keeps every printing a set has, basics
        included, so a set's own Plains is just another print row."""
        rows = self.session.execute(
            select(Card, CardPrint)
            .join(CardPrint, CardPrint.oracle_id == Card.oracle_id)
            .where(CardPrint.set_code == set_code, Card.name.in_(BASIC_COLOURS))
            .order_by(CardPrint.collector_number)
        )
        out: dict[str, CardInfo] = {}
        for card, printing in rows:
            # Sorted by collector number, so the first is the plain art.
            out.setdefault(BASIC_COLOURS[card.name], _card_info(card, printing))
        return out


def _card_info(card: Card, printing: CardPrint | None) -> CardInfo:
    return CardInfo(
        name=card.name,
        mana_cost=card.mana_cost,
        type_line=card.type_line,
        cmc=card.cmc,
        colors=card.colors,
        rarity=printing.rarity if printing else None,
        image_normal=printing.image_normal if printing else None,
        image_art_crop=printing.image_art_crop if printing else None,
    )


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def get_review_service(
    session: Annotated[Session, Depends(get_session)],
) -> ReviewService:
    return ReviewService(
        store=SqlReplayStore(session),
        catalog=SqlCatalog(session),
        fetch=fetch_seventeen_lands_draft,
        limiter=RateLimiter(
            SqlLedger(session),
            {
                "fetch": Limits(
                    per_minute=settings.fetch_limit_per_minute,
                    per_day=settings.fetch_limit_per_day,
                ),
                "deck": Limits(
                    per_minute=settings.deck_limit_per_minute,
                    per_day=settings.deck_limit_per_day,
                ),
            },
        ),
        supported_sets=settings.supported_set_codes,
    )
