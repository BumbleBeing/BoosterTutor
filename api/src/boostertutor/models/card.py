"""Card identity: what exists, and how it was printed.

Split into two tables because Limited cares about printings, not just cards.
The same card can be uncommon in one set and rare in another, for example.
"""

import datetime as dt
import uuid

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CardSet(Base):
    """A Magic set. Named CardSet because `Set` would shadow the builtin."""

    __tablename__ = "sets"

    set_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    released_at: Mapped[dt.date | None] = mapped_column(Date())
    set_type: Mapped[str] = mapped_column(String(32))
    is_draftable: Mapped[bool] = mapped_column(Boolean(), default=False)


class Card(Base):
    """One row per Oracle card - the rules-text identity, independent of printing."""

    __tablename__ = "cards"

    oracle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    mana_cost: Mapped[str | None] = mapped_column(String(64))
    cmc: Mapped[float] = mapped_column(Float())
    type_line: Mapped[str] = mapped_column(String(128))
    oracle_text: Mapped[str | None] = mapped_column(Text())

    # Colours stored as sorted WUBRG letters: "" colourless, "U" mono-blue, "BR" gold.
    # Scryfall gives arrays, but this form makes the archetype joins we care about
    # trivial - 17Lands expresses colour pairs the same way ("BR", "WU"). The cost
    # is that "cards containing blue" becomes a LIKE query rather than an index hit.
    colors: Mapped[str] = mapped_column(String(5), default="")
    color_identity: Mapped[str] = mapped_column(String(5), default="")

    # Strings, not integers: power can be "*", "1+*", or "?".
    power: Mapped[str | None] = mapped_column(String(8))
    toughness: Mapped[str | None] = mapped_column(String(8))

    layout: Mapped[str] = mapped_column(String(32))
    keywords: Mapped[list[str]] = mapped_column(JSONB(), default=list)


class CardPrint(Base):
    """One row per printing. Rarity and images live here, not on Card."""

    __tablename__ = "card_prints"

    scryfall_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    oracle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cards.oracle_id", ondelete="CASCADE"), index=True
    )
    set_code: Mapped[str] = mapped_column(
        ForeignKey("sets.set_code", ondelete="CASCADE"), index=True
    )
    collector_number: Mapped[str] = mapped_column(String(16))
    rarity: Mapped[str] = mapped_column(String(16))
    image_normal: Mapped[str | None] = mapped_column(String(512))
    image_art_crop: Mapped[str | None] = mapped_column(String(512))

    # MTG Arena's id for this printing. Arena's Player.log names cards by it,
    # which is how a pasted Arena draft log (Phase 3) finds its cards. The
    # 17Lands public datasets name cards by name instead, so this is not their
    # join key. Null for printings never released on Arena.
    arena_id: Mapped[int | None] = mapped_column(Integer(), index=True)
