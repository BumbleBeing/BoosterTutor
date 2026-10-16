"""Claude's stored prose about a draft: its Pick Notes and Draft Summary (ADR 0031 s5).

`draft_reviews` is one owner's review of one cached draft: the Draft
Summary, the deck it was written about (`reviewed_deck`) and the latest deck
submitted since (`current_deck`). `pick_notes` holds its Pick Notes, one row
each, written lazily as picks are opened. They are a table of their own, not
a JSON map on the review, so two notes written at the same moment can't
overwrite each other.

Verdicts are never stored: they are recomputed on every request. Prose is
stored because it costs money to write. So each piece of prose records the
Stats Snapshot it was written against, and the page tags it "written against
older stats" once today's snapshot differs.

In Phase 5 only admin-key calls write here, so `user_id` is null on every
row. Phase 6 deletes those rows and makes it NOT NULL (ADR 0021).
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import ForeignKey, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import DATE, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DraftReviewRow(Base):
    __tablename__ = "draft_reviews"
    __table_args__ = (
        # One review per draft and owner. NULLS NOT DISTINCT (Postgres 15+)
        # makes two null owners count as the same owner, so there is one
        # admin review per draft rather than one per request.
        UniqueConstraint(
            "draft_id",
            "user_id",
            name="uq_draft_reviews_draft_id_user_id",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    draft_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("drafts.draft_id", ondelete="CASCADE")
    )
    # The Supabase Auth user, from Phase 6. Null: written with the Admin Key.
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Decks as the deck builder sends them (`SubmittedDeck`):
    # {"cards": [oracle ids], "basics": {"W": 8, ...}}.
    # The deck the Draft Summary was written about. Null until a summary
    # succeeds, so a failed one is tried again on the next deck.
    reviewed_deck: Mapped[dict[str, Any] | None] = mapped_column(JSONB())
    # The latest deck submitted. Later decks get Deck Ratings only.
    current_deck: Mapped[dict[str, Any] | None] = mapped_column(JSONB())

    # The Draft Summary: {"draft_arc", "deck", "lesson", "key_picks"}.
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB())
    summary_prompt_version: Mapped[str | None] = mapped_column(String(32))
    summary_model: Mapped[str | None] = mapped_column(String(64))
    summary_stats_snapshot: Mapped[dt.date | None] = mapped_column(DATE())


class PickNoteRow(Base):
    __tablename__ = "pick_notes"

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("draft_reviews.id", ondelete="CASCADE"),
        primary_key=True,
    )
    pack_number: Mapped[int] = mapped_column(SmallInteger(), primary_key=True)
    pick_number: Mapped[int] = mapped_column(SmallInteger(), primary_key=True)
    # "critical" or "narrow" (ADR 0024 s2).
    kind: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text())
    prompt_version: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    # The 17Lands Stats Snapshot the note was written against.
    stats_snapshot: Mapped[dt.date] = mapped_column(DATE())
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
