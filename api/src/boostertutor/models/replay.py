"""The Replay Cache, and the ledger behind the fetch rate limit (ADR 0031 s5-6).

`drafts` keeps one parsed 17Lands draft per draft id, so a draft is fetched
from 17lands.com once however often it is reviewed (ADR 0023). It is public
data with no user and no review: verdicts are never stored here, they are
recomputed from this log and the current statistics on every request.

`fetch_attempts` is the limiter's counter. It lives in Postgres rather than
in memory because Render restarts instances. It holds a salted hash of the
client address, never the address itself.
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


class FetchAttempt(Base):
    """One submission that needed a 17Lands fetch."""

    __tablename__ = "fetch_attempts"
    __table_args__ = (
        Index("ix_fetch_attempts_client_attempted", "client", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger(), Identity(), primary_key=True)
    # SHA-256 of the client address and a secret salt, in hex.
    client: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
