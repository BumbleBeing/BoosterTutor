"""The real `ReviewService`, built over a Postgres session.

`ClaudeCoach` is the real `Coach`, with `llm_calls` as its ledger.

Each request gets its own session and its own service (`get_review_service`
is a FastAPI dependency). Tests replace that dependency with a service built
from in-memory fakes (`tests/review_world.py`).
"""

import uuid
from collections.abc import Iterable, Iterator
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..analysis.deck_rating import DeckRatingModel
from ..analysis.draft import FormatInputs
from ..briefing import CardFacts
from ..briefing.primer import format_primer
from ..card_facts import load_card_facts
from ..config import settings
from ..db import SessionLocal
from ..format_inputs import load_deck_rating_model, load_format_inputs, name_index
from ..format_primer import load_primer_facts
from ..llm import draft_summary, pick_note
from ..llm.client import anthropic_client
from ..llm.coach import ClaudeCoach
from ..llm.spending import DbLedger
from ..models import Card, CardPrint, Draft, DraftReviewRow, PickNoteRow
from ..schemas import DraftLog
from ..schemas.coach import SavedNote, SavedReview, SavedSummary
from ..schemas.deck_submission import SubmittedDeck
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

    def card_facts(
        self, set_code: str, ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, CardFacts]:
        return load_card_facts(self.session, set_code, ids)

    def primer(self, set_code: str, event_type: str) -> str:
        return format_primer(load_primer_facts(self.session, set_code, event_type))


class SqlSavedReviews:
    """`SavedReviews` over `draft_reviews` and `pick_notes`."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _row(self, draft_id: str, user_id: uuid.UUID | None) -> DraftReviewRow | None:
        # `IS NOT DISTINCT FROM` matches a null owner to a null owner, as the
        # table's unique constraint does; `=` would never match a null.
        return self.session.scalars(
            select(DraftReviewRow).where(
                DraftReviewRow.draft_id == draft_id,
                DraftReviewRow.user_id.is_not_distinct_from(user_id),
            )
        ).first()

    def _row_or_new(self, draft_id: str, user_id: uuid.UUID | None) -> uuid.UUID:
        """The review's id, creating an empty review first if there is none."""
        self.session.execute(
            insert(DraftReviewRow)
            .values(id=uuid.uuid4(), draft_id=draft_id, user_id=user_id)
            .on_conflict_do_nothing(constraint="uq_draft_reviews_draft_id_user_id")
        )
        row = self._row(draft_id, user_id)
        assert row is not None  # inserted above, or already there
        return row.id

    def get(self, draft_id: str, user_id: uuid.UUID | None) -> SavedReview | None:
        row = self._row(draft_id, user_id)
        if row is None:
            return None
        notes = self.session.scalars(
            select(PickNoteRow).where(PickNoteRow.review_id == row.id)
        )
        return SavedReview(
            notes=[_saved_note(n) for n in notes],
            summary=(
                SavedSummary(
                    **row.summary,
                    prompt_version=row.summary_prompt_version,
                    model=row.summary_model,
                    stats_snapshot=row.summary_stats_snapshot,
                )
                if row.summary is not None
                else None
            ),
            reviewed_deck=_deck(row.reviewed_deck),
            current_deck=_deck(row.current_deck),
        )

    def add_note(
        self, draft_id: str, user_id: uuid.UUID | None, note: SavedNote
    ) -> SavedNote:
        review_id = self._row_or_new(draft_id, user_id)
        # A second request for the same pick, racing this one, may have
        # stored a note already: keep that one and return it.
        self.session.execute(
            insert(PickNoteRow)
            .values(review_id=review_id, **note.model_dump())
            .on_conflict_do_nothing()
        )
        self.session.commit()
        stored = self.session.get(
            PickNoteRow, (review_id, note.pack_number, note.pick_number)
        )
        assert stored is not None
        return _saved_note(stored)

    def save_deck(
        self,
        draft_id: str,
        user_id: uuid.UUID | None,
        deck: SubmittedDeck,
        summary: SavedSummary | None,
    ) -> None:
        review_id = self._row_or_new(draft_id, user_id)
        row = self.session.get(DraftReviewRow, review_id)
        assert row is not None
        stored = deck.model_dump(mode="json")
        row.current_deck = stored
        if summary is not None:
            row.reviewed_deck = stored
            row.summary = summary.model_dump(
                mode="json", include={"draft_arc", "deck", "lesson", "key_picks"}
            )
            row.summary_prompt_version = summary.prompt_version
            row.summary_model = summary.model
            row.summary_stats_snapshot = summary.stats_snapshot
        self.session.commit()


def _saved_note(row: PickNoteRow) -> SavedNote:
    return SavedNote(
        pack_number=row.pack_number,
        pick_number=row.pick_number,
        kind=row.kind,  # type: ignore[arg-type]  # stored from a NoteKind
        note=row.note,
        prompt_version=row.prompt_version,
        model=row.model,
        stats_snapshot=row.stats_snapshot,
    )


def _deck(stored: dict[str, Any] | None) -> SubmittedDeck | None:
    return SubmittedDeck.model_validate(stored) if stored is not None else None


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
        saved=SqlSavedReviews(session),
        coach=lambda: ClaudeCoach(
            anthropic_client(),
            DbLedger(session),
            cap=settings.daily_spend_cap_usd,
            pick_note_prompt=pick_note.load_prompt(pick_note.PROMPT_VERSION),
            summary_prompt=draft_summary.load_prompt(draft_summary.PROMPT_VERSION),
        ),
    )
