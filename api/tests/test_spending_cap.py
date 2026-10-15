"""The daily spending cap (ADR 0027 s3).

Today's spend is summed from `llm_calls`; once it reaches the cap, no
further Claude call is made until the next UTC day. The database half is
`DbLedger`; here the cap is checked against a ledger in memory.
"""

import datetime as dt
from decimal import Decimal

import pytest

from boostertutor.llm.spending import (
    RETIRED_MESSAGE,
    SpendingCapReached,
    check_spending_cap,
    start_of_day,
)


class Ledger:
    def __init__(self, spent: str) -> None:
        self.spent = Decimal(spent)

    def spent_today(self) -> Decimal:
        return self.spent


def test_under_the_cap_a_call_may_go_ahead() -> None:
    check_spending_cap(Ledger("4.999999"), Decimal("5.00"))


def test_at_the_cap_the_coach_retires_for_the_day() -> None:
    with pytest.raises(SpendingCapReached) as raised:
        check_spending_cap(Ledger("5.000000"), Decimal("5.00"))
    assert str(raised.value) == RETIRED_MESSAGE
    assert RETIRED_MESSAGE == (
        "The coach has retired for the day, please come back tomorrow."
    )


def test_the_day_is_the_utc_day() -> None:
    """23:30 in Los Angeles on the 15th is 06:30 UTC on the 16th."""
    la = dt.timezone(dt.timedelta(hours=-7))
    now = dt.datetime(2026, 10, 15, 23, 30, tzinfo=la)
    assert start_of_day(now) == dt.datetime(2026, 10, 16, tzinfo=dt.UTC)


def test_a_naive_time_is_refused() -> None:
    """A time with no zone could be any day; better to fail than to guess."""
    with pytest.raises(ValueError):
        start_of_day(dt.datetime(2026, 10, 15, 12, 0))  # noqa: DTZ001, the point
