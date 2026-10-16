"""The per-IP limit on submissions that need a 17Lands fetch (ADR 0031 s6).

The limiter's counting is tested against an in-memory ledger; the Postgres
ledger is the same three calls over one table.
"""

import datetime as dt

import pytest

from boostertutor.rate_limit import (
    FetchLimiter,
    FetchLimits,
    RateLimited,
    client_key,
)

START = dt.datetime(2026, 10, 16, 12, 0, tzinfo=dt.UTC)


class MemoryLedger:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dt.datetime]] = []

    def count_since(self, key: str, since: dt.datetime) -> int:
        return sum(1 for k, at in self.rows if k == key and at > since)

    def record(self, key: str, at: dt.datetime) -> None:
        self.rows.append((key, at))

    def prune(self, before: dt.datetime) -> None:
        self.rows = [(k, at) for k, at in self.rows if at >= before]


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> dt.datetime:
        return self.now


def make(
    per_minute: int = 2, per_day: int = 4
) -> tuple[FetchLimiter, Clock, MemoryLedger]:
    clock, ledger = Clock(), MemoryLedger()
    limiter = FetchLimiter(ledger, FetchLimits(per_minute, per_day), clock)
    return limiter, clock, ledger


def test_submissions_under_the_limit_pass_and_are_recorded() -> None:
    limiter, _, ledger = make()
    limiter.check_and_record("a")
    limiter.check_and_record("a")
    assert len(ledger.rows) == 2


def test_the_per_minute_limit_blocks_and_says_when_to_retry() -> None:
    limiter, _, ledger = make()
    limiter.check_and_record("a")
    limiter.check_and_record("a")
    with pytest.raises(RateLimited) as caught:
        limiter.check_and_record("a")
    assert caught.value.window == "minute"
    assert caught.value.retry_after == 60
    assert len(ledger.rows) == 2  # a refused submission is not recorded


def test_the_minute_window_slides() -> None:
    limiter, clock, _ = make()
    limiter.check_and_record("a")
    limiter.check_and_record("a")
    clock.now += dt.timedelta(seconds=61)
    limiter.check_and_record("a")


def test_the_daily_limit_blocks_after_the_minute_windows_pass() -> None:
    limiter, clock, _ = make()
    for _ in range(4):
        limiter.check_and_record("a")
        clock.now += dt.timedelta(minutes=2)
    with pytest.raises(RateLimited) as caught:
        limiter.check_and_record("a")
    assert caught.value.window == "day"
    assert caught.value.retry_after == 3600


def test_the_day_window_slides() -> None:
    limiter, clock, _ = make()
    for _ in range(4):
        limiter.check_and_record("a")
        clock.now += dt.timedelta(minutes=2)
    clock.now += dt.timedelta(hours=24)
    limiter.check_and_record("a")


def test_each_client_has_its_own_allowance() -> None:
    limiter, _, _ = make()
    limiter.check_and_record("a")
    limiter.check_and_record("a")
    limiter.check_and_record("b")


def test_old_rows_are_pruned() -> None:
    limiter, clock, ledger = make()
    limiter.check_and_record("a")
    clock.now += dt.timedelta(days=3)
    limiter.check_and_record("a")
    assert len(ledger.rows) == 1


# --------------------------------------------------------------------------
# Who is asking
# --------------------------------------------------------------------------


def test_the_key_is_a_salted_hash_not_the_address() -> None:
    key = client_key("203.0.113.9", None, proxy_hops=0, salt="s")
    assert "203.0.113.9" not in key
    assert key == client_key("203.0.113.9", None, proxy_hops=0, salt="s")
    assert key != client_key("203.0.113.9", None, proxy_hops=0, salt="other")
    assert key != client_key("203.0.113.10", None, proxy_hops=0, salt="s")


def test_behind_no_proxy_the_forwarded_header_is_ignored() -> None:
    # Anyone can send X-Forwarded-For; trusting it would let a client pick its
    # own identity and so dodge the limit.
    spoofed = client_key("203.0.113.9", "1.2.3.4", proxy_hops=0, salt="s")
    assert spoofed == client_key("203.0.113.9", None, proxy_hops=0, salt="s")


def test_behind_a_proxy_the_entry_it_appended_is_used() -> None:
    # Each proxy appends the address it saw, so the last entry is the one our
    # own proxy wrote; anything to its left the client could have forged.
    header = "6.6.6.6, 198.51.100.7"
    assert client_key("10.0.0.1", header, proxy_hops=1, salt="s") == client_key(
        "198.51.100.7", None, proxy_hops=0, salt="s"
    )


def test_a_header_shorter_than_the_proxy_chain_falls_back_to_the_socket() -> None:
    assert client_key("10.0.0.1", "1.1.1.1", proxy_hops=2, salt="s") == client_key(
        "10.0.0.1", None, proxy_hops=0, salt="s"
    )
