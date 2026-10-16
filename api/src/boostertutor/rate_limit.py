"""A per-client limit on submissions that need a 17Lands fetch (ADR 0031 s6).

It exists so BoosterTutor can't be used as a proxy to pull 17Lands' drafts in
volume (ADR 0023). Only a submission that really calls 17lands.com counts: a
draft already in the Replay Cache is answered without a request and is free.

The counter is a Postgres table, not memory, because Render restarts
instances and a restart would otherwise hand everyone a fresh allowance.
Clients are told apart by a salted hash of their address, so the table never
holds an address.
"""

import datetime as dt
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .models import FetchAttempt

MINUTE = dt.timedelta(minutes=1)
DAY = dt.timedelta(days=1)


@dataclass(frozen=True)
class FetchLimits:
    per_minute: int
    per_day: int


class RateLimited(Exception):
    """The client is out of fetches. `retry_after` is in seconds."""

    def __init__(self, window: Literal["minute", "day"], retry_after: int) -> None:
        super().__init__(f"too many 17Lands fetches in the last {window}")
        self.window = window
        self.retry_after = retry_after


class Ledger(Protocol):
    """Where attempts are remembered: Postgres in production."""

    def count_since(self, key: str, since: dt.datetime) -> int: ...
    def record(self, key: str, at: dt.datetime) -> None: ...
    def prune(self, before: dt.datetime) -> None: ...


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class FetchLimiter:
    def __init__(
        self,
        ledger: Ledger,
        limits: FetchLimits,
        clock: Callable[[], dt.datetime] = _utc_now,
    ) -> None:
        self.ledger = ledger
        self.limits = limits
        self.clock = clock

    def check_and_record(self, key: str) -> None:
        """Let the client fetch, or raise `RateLimited`.

        The attempt is recorded before the fetch happens, so a fetch that
        fails still counts: otherwise a client could hammer 17Lands with ids
        that don't exist and never run out.
        """
        now = self.clock()
        # Rows older than the longest window can never matter again.
        self.ledger.prune(now - DAY)
        if self.ledger.count_since(key, now - MINUTE) >= self.limits.per_minute:
            raise RateLimited("minute", 60)
        if self.ledger.count_since(key, now - DAY) >= self.limits.per_day:
            # The true wait could be up to a day; an hour is a polite hint.
            raise RateLimited("day", 3600)
        self.ledger.record(key, now)


class SqlLedger:
    """`Ledger` over the `fetch_attempts` table. Each call commits, so an
    attempt is kept even if the request that made it later fails."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def count_since(self, key: str, since: dt.datetime) -> int:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(FetchAttempt)
                .where(FetchAttempt.client == key, FetchAttempt.created_at > since)
            )
            or 0
        )

    def record(self, key: str, at: dt.datetime) -> None:
        self.session.add(FetchAttempt(client=key, created_at=at))
        self.session.commit()

    def prune(self, before: dt.datetime) -> None:
        self.session.execute(
            delete(FetchAttempt).where(FetchAttempt.created_at < before)
        )
        self.session.commit()


def client_key(
    socket_host: str | None,
    forwarded_for: str | None,
    *,
    proxy_hops: int,
    salt: str,
) -> str:
    """A stable, anonymous identity for whoever is calling.

    Anyone can send an `X-Forwarded-For` header, so it is only believed as
    far as our own proxies go: each appends the address it saw, so the entry
    `proxy_hops` from the right is the one our outermost proxy wrote.
    Anything further left is whatever the client claimed.
    """
    host = socket_host or "unknown"
    if proxy_hops > 0 and forwarded_for:
        entries = [e.strip() for e in forwarded_for.split(",") if e.strip()]
        if len(entries) >= proxy_hops:
            host = entries[-proxy_hops]
    return hashlib.sha256(f"{salt}:{host}".encode()).hexdigest()
