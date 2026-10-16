"""The Replay Cache, and the counter behind the rate limits (ADR 0031 s5-6).

`drafts` keeps one parsed 17Lands draft per draft id, so a draft is fetched
from 17lands.com once however often it is reviewed (ADR 0023). It is public
data with no user and no review: verdicts are never stored here, they are
recomputed from this log and the current statistics on every request.

`rate_limit_events` is the limiter's counter (`review/rate_limit.py`). It
lives in Postgres rather than in memory because Render restarts instances.
It holds a salted hash of the client address, never the address itself.
"""

import datetime as dt
from typing import Any

from sqlalchemy import BigInteger, Identity, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Draft(Base):
    __tablename__ = "drafts"

    # The 17Lands draft id: 32 lowercase hex characters.
    draft_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    set_code: Mapped[str] = mapped_column(String(8), index=True)
    # The parsed `DraftLog`, as `DraftLog.model_dump(mode="json")`.
    log: Mapped[dict[str, Any]] = mapped_column(JSONB())
    fetched_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class RateLimitEvent(Base):
    """One request that counted against a client's allowance."""

    __tablename__ = "rate_limit_events"
    __table_args__ = (
        # Every query asks "how many in this bucket, from this client, since
        # when", so the index is in that order.
        Index(
            "ix_rate_limit_events_bucket_client_created",
            "bucket",
            "client",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger(), Identity(), primary_key=True)
    # Which allowance it counts against: "fetch" or "deck".
    bucket: Mapped[str] = mapped_column(String(16))
    # SHA-256 of the client address and a secret salt, in hex.
    client: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
