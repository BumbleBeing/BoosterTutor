"""How cards and archetypes actually perform, from the 17Lands public datasets.

Every table is keyed by `snapshot_date`: the day 17Lands last updated the dump
the figures were computed from. Win rates move a lot in a set's first weeks
and then settle, so keeping each snapshot lets a draft be explained with the
numbers as they stood then, and lets "why did the advice change?" be
answered. The `*_current` views (created in the migration) pick the latest
snapshot, so ordinary queries never have to.

Win rates are percentage points (56.3, not 0.563), the unit the fitness
function works in. Every rate travels with the game count behind it: a 62%
GIH WR over 180 games is noise, and the analysis needs to be able to say so.
"""

import datetime as dt
import uuid

from sqlalchemy import Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class _CardRates:
    """The per-card win rates, shared by the overall and archetype tables.

    GP: the card was in the deck. OH: in the opening hand. GD: drawn after
    the opening hand. GIH: in hand at some point (OH or GD). GND: in the deck
    but never drawn. IWD = GIH WR - GND WR, the card's own contribution.
    """

    gp_wr: Mapped[float | None] = mapped_column(Float())
    gp_games: Mapped[int] = mapped_column(Integer(), default=0)
    oh_wr: Mapped[float | None] = mapped_column(Float())
    oh_games: Mapped[int] = mapped_column(Integer(), default=0)
    gd_wr: Mapped[float | None] = mapped_column(Float())
    gd_games: Mapped[int] = mapped_column(Integer(), default=0)
    gih_wr: Mapped[float | None] = mapped_column(Float())
    gih_games: Mapped[int] = mapped_column(Integer(), default=0)
    gnd_wr: Mapped[float | None] = mapped_column(Float())
    gnd_games: Mapped[int] = mapped_column(Integer(), default=0)
    iwd: Mapped[float | None] = mapped_column(Float())


class CardDraftStats(_CardRates, Base):
    """One card in one format, overall."""

    __tablename__ = "card_draft_stats"

    set_code: Mapped[str] = mapped_column(
        ForeignKey("sets.set_code", ondelete="CASCADE"), primary_key=True
    )
    event_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    oracle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cards.oracle_id", ondelete="CASCADE"), primary_key=True
    )
    snapshot_date: Mapped[dt.date] = mapped_column(Date(), primary_key=True)

    # From the draft dump. ALSA: average last pick at which the card was still
    # in a pack. ATA: average pick at which it was taken. Both 1-based.
    seen_count: Mapped[int] = mapped_column(Integer(), default=0)
    alsa: Mapped[float | None] = mapped_column(Float())
    pick_count: Mapped[int] = mapped_column(Integer(), default=0)
    ata: Mapped[float | None] = mapped_column(Float())


class CardArchetypeStats(_CardRates, Base):
    """One card in one format, in decks of one two-colour archetype only."""

    __tablename__ = "card_archetype_stats"

    set_code: Mapped[str] = mapped_column(
        ForeignKey("sets.set_code", ondelete="CASCADE"), primary_key=True
    )
    event_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    oracle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cards.oracle_id", ondelete="CASCADE"), primary_key=True
    )
    # Sorted WUBRG, as 17Lands and the glossary write it: "BR", "WU".
    archetype: Mapped[str] = mapped_column(String(2), primary_key=True)
    snapshot_date: Mapped[dt.date] = mapped_column(Date(), primary_key=True)


class ArchetypeStats(Base):
    """How decks of one two-colour archetype do, whatever their cards."""

    __tablename__ = "archetype_stats"

    set_code: Mapped[str] = mapped_column(
        ForeignKey("sets.set_code", ondelete="CASCADE"), primary_key=True
    )
    event_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    archetype: Mapped[str] = mapped_column(String(2), primary_key=True)
    snapshot_date: Mapped[dt.date] = mapped_column(Date(), primary_key=True)
    wins: Mapped[int] = mapped_column(Integer())
    games: Mapped[int] = mapped_column(Integer())
    win_rate: Mapped[float | None] = mapped_column(Float())
