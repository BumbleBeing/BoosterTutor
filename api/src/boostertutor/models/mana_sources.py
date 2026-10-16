"""Each set's Fixers: the cards that count as Colour Sources or as part of a land (ADR 0028).

Hand-authored, like the tag taxonomy, and loaded from the same file
(`api/data/taxonomy/{set}.json`, the `mana_sources` section). The loader
resolves each entry's kind, expected Treasures and overrides into finished
weights, so a source kind needs no table of its own: change a kind, and
reload the file.
"""

import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CardManaSource(Base):
    """One Fixer in one set. A card with no row is no Fixer."""

    __tablename__ = "card_mana_sources"
    __table_args__ = (
        CheckConstraint(
            "color_weight >= 0 AND land_weight >= 0 AND min_mana_value >= 0",
            name="weights_not_negative",
        ),
    )

    set_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    oracle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cards.oracle_id", ondelete="CASCADE"),
        primary_key=True,
    )
    # A source kind from the file: fetch_basic, treasure, land_tutor, ...
    kind: Mapped[str] = mapped_column(String(32))
    # What the card fixes for, as sorted WUBRG letters ("G", "BR", "WUBRG"),
    # or "basics": whichever basic lands the deck runs.
    colors: Mapped[str] = mapped_column(String(8))
    # How many Treasures the card usually makes; treasure kinds only.
    expected: Mapped[float | None] = mapped_column(Float())
    # Resolved: how much of a Colour Source one copy is, toward spells of at
    # least `min_mana_value` (0: any), and how much of a land it is.
    color_weight: Mapped[float] = mapped_column(Float())
    land_weight: Mapped[float] = mapped_column(Float())
    min_mana_value: Mapped[int] = mapped_column(Integer())
    # Why an entry overrides its kind, when it does.
    notes: Mapped[str | None] = mapped_column(Text())
