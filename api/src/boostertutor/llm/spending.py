"""The daily spending cap: a global kill switch on Claude calls (ADR 0027 s3).

Before every call, today's spend is read from `llm_calls`. Once it reaches
`settings.daily_spend_cap_usd`, no further call is made until the next UTC
day, and the user sees `RETIRED_MESSAGE` where the prose would be. The
Python review carries on regardless: verdicts, scores and Noted Pick
markers need no Claude (ADR 0027 s4).

A "ledger" is anything that can say what today cost and record a call.
`DbLedger` is the real one; the tests use one in memory, since nothing in
the test suite opens a database connection.
"""

import datetime as dt
from decimal import Decimal
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import LlmCall

RETIRED_MESSAGE = "The coach has retired for the day, please come back tomorrow."


class SpendingCapReached(RuntimeError):
    def __init__(self) -> None:
        super().__init__(RETIRED_MESSAGE)


class SpendReader(Protocol):
    def spent_today(self) -> Decimal: ...


class Ledger(SpendReader, Protocol):
    def record(self, call: LlmCall) -> None: ...


def start_of_day(now: dt.datetime) -> dt.datetime:
    """Midnight UTC at the start of `now`'s UTC day.

    UTC, not local time: the cap is global, and a server's local time is
    whatever Render sets it to.
    """
    if now.tzinfo is None:
        raise ValueError("a time without a time zone could be any day")
    utc = now.astimezone(dt.UTC)
    return dt.datetime(utc.year, utc.month, utc.day, tzinfo=dt.UTC)


def check_spending_cap(ledger: SpendReader, cap: Decimal) -> None:
    """Raise `SpendingCapReached` if today's spend has reached `cap`."""
    if ledger.spent_today() >= cap:
        raise SpendingCapReached()


class DbLedger:
    """`llm_calls` as the ledger. Each recorded call is committed at once.

    Committing per call, rather than with the caller's other work, is
    deliberate: a call is billed whether or not what follows succeeds, so
    its row must survive a later rollback.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def spent_today(self) -> Decimal:
        since = start_of_day(dt.datetime.now(dt.UTC))
        total = self.session.scalar(
            select(func.coalesce(func.sum(LlmCall.cost_usd), 0)).where(
                LlmCall.created_at >= since
            )
        )
        return Decimal(total or 0)

    def record(self, call: LlmCall) -> None:
        self.session.add(call)
        self.session.commit()
