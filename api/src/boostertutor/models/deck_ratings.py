"""Each format's fitted Deck Ratings model (ADR 0026 s2).

Measured, not authored: rebuilt from the cached 17Lands game dump by
`python -m boostertutor.ingest deck-ratings`. Keyed by the dump's snapshot
date, so a practice draft can be rated against the Stats Snapshot it was
drafted under (ADR 0020). A format with no row reads "not enough data to
rate".

No foreign key to `sets`, as with `format_constants`.
"""

import datetime as dt
from typing import Any

from sqlalchemy import Date, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DeckRatingModelRow(Base):
    """One fit: the regression and the percentile tables, for one format and dump.

    JSONB rather than child tables: the model is read whole, never queried
    by metric, and its metrics are a list in code that may grow.
    """

    __tablename__ = "deck_rating_models"

    set_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    snapshot_date: Mapped[dt.date] = mapped_column(Date(), primary_key=True)

    decks: Mapped[int] = mapped_column(Integer())  # distinct 40-card decks scored
    games: Mapped[int] = mapped_column(Integer())  # games the regression saw
    # Log-odds of a game win, in each metric's own units. A metric that never
    # varied in the format is absent.
    intercept: Mapped[float] = mapped_column(Float())
    coefficients: Mapped[dict[str, float]] = mapped_column(JSONB())
    standard_errors: Mapped[dict[str, float]] = mapped_column(JSONB())
    # metric -> the 0th to 100th percentiles among the format's decks, and
    # "win_rate" -> the same for the regression's predicted win rate.
    quantiles: Mapped[dict[str, Any]] = mapped_column(JSONB())
    source: Mapped[str] = mapped_column(Text())  # the dump's file name
    fitted_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
