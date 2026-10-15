"""One row per Claude API call: what it cost, and how it went (ADR 0024 s8).

Three jobs. It is the spending cap's ledger: before any call, today's
`cost_usd` is summed, and over `daily_spend_cap_usd` no call is made
(ADR 0027). It is how cost per Pick Note and per Draft Summary is stated
from data rather than estimated (development plan, Phase 4). And it shows
whether the 1-hour prompt cache is earning its doubled write price: cache
reads against cache writes, call by call.

Every call leaves a row, including one that failed validation and was
retried, because the API bills it either way.
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import BigInteger, Identity, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(BigInteger(), Identity(), primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), index=True
    )
    # "pick_note" or "draft_summary".
    purpose: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    # The prompt file's name without ".md": "pick_note.v1".
    prompt_version: Mapped[str] = mapped_column(String(32))
    # The Supabase Auth user the call was made for. Null **only** for eval
    # and CLI runs: every call made for a user names them (ADR 0021).
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Which draft the call was for, "17lands:<draft id>". A draft counts
    # against its user's daily allowance once, at its first call (ADR 0027).
    draft_key: Mapped[str | None] = mapped_column(String(64), index=True)
    # Which part of the draft: "P1p12" for a Pick Note.
    subject: Mapped[str | None] = mapped_column(String(16))

    input_tokens: Mapped[int] = mapped_column(Integer())  # uncached input only
    cache_read_tokens: Mapped[int] = mapped_column(Integer())
    cache_write_tokens: Mapped[int] = mapped_column(Integer())
    output_tokens: Mapped[int] = mapped_column(Integer())
    # Computed by `llm.pricing` at call time, so a later price change does
    # not rewrite history.
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    latency_ms: Mapped[int] = mapped_column(Integer())

    # "succeeded"; "invalid": the response failed validation; "refused":
    # stop_reason was refusal; "error": the API call itself failed.
    status: Mapped[str] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(Text())
    # Anthropic's request id, to quote when reporting a problem to them.
    request_id: Mapped[str | None] = mapped_column(String(64))
