"""Per-client limits for anonymous requests (ADR 0031 s6).

Two buckets, each with its own allowance:

- `fetch`: submitting a draft link that needs a 17lands.com request. It
  exists so BoosterTutor can't be used to pull 17Lands' drafts in volume
  (ADR 0023). A draft already in the Replay Cache costs nothing.
- `deck`: submitting a deck for Deck Ratings. Cheap, so more generous.

The counter is a Postgres table, not memory, because Render restarts
instances and a restart would otherwise hand everyone a fresh allowance.
Clients are told apart by a salted hash of their address, so the table never
holds an address.
"""

import datetime as dt
import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import RateLimitEvent

Bucket = Literal["fetch", "deck"]

MINUTE = dt.timedelta(minutes=1)
DAY = dt.timedelta(days=1)


@dataclass(frozen=True)
class Limits:
    per_minute: int
    per_day: int


class RateLimited(Exception):
    """The client is out of allowance in `bucket`. `retry_after` is in seconds."""

    def __init__(
        self, bucket: Bucket, window: Literal["minute", "day"], retry_after: int
    ) -> None:
        super().__init__(f"too many {bucket} requests in the last {window}")
        self.bucket = bucket
        self.window = window
        self.retry_after = retry_after


class Ledger(Protocol):
    """Where requests are remembered: Postgres in production."""

    def count_since(self, bucket: Bucket, client: str, since: dt.datetime) -> int: ...
    def record(self, bucket: Bucket, client: str, at: dt.datetime) -> None: ...
    def prune(self, before: dt.datetime) -> None: ...


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class RateLimiter:
    def __init__(
        self,
        ledger: Ledger,
        limits: Mapping[Bucket, Limits],
        clock: Callable[[], dt.datetime] = _utc_now,
    ) -> None:
        self.ledger = ledger
        self.limits = limits
        self.clock = clock

    def check_and_record(self, bucket: Bucket, client: str) -> None:
        """Let the request through and count it, or raise `RateLimited`.

        The request is counted before the work happens, so one that fails
        still counts: otherwise a client could hammer 17Lands with ids that
        don't exist, or send bad decks, and never run out.
        """
        limits = self.limits[bucket]
        now = self.clock()
        # Rows older than the longest window can never matter again.
        self.ledger.prune(now - DAY)
        if self.ledger.count_since(bucket, client, now - MINUTE) >= limits.per_minute:
            raise RateLimited(bucket, "minute", 60)
        if self.ledger.count_since(bucket, client, now - DAY) >= limits.per_day:
            # The true wait could be up to a day; an hour is a polite hint.
            raise RateLimited(bucket, "day", 3600)
        self.ledger.record(bucket, client, now)


class SqlLedger:
    """`Ledger` over the `rate_limit_events` table. Each call commits, so a
    request is counted even if the work it asked for later fails."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def count_since(self, bucket: Bucket, client: str, since: dt.datetime) -> int:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(RateLimitEvent)
                .where(
                    RateLimitEvent.bucket == bucket,
                    RateLimitEvent.client == client,
                    RateLimitEvent.created_at > since,
                )
            )
            or 0
        )

    def record(self, bucket: Bucket, client: str, at: dt.datetime) -> None:
        self.session.add(RateLimitEvent(bucket=bucket, client=client, created_at=at))
        self.session.commit()

    def prune(self, before: dt.datetime) -> None:
        self.session.execute(
            delete(RateLimitEvent).where(RateLimitEvent.created_at < before)
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
