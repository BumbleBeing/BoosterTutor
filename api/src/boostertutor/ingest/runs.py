"""Recording every ingest run in `ingest_runs`, whatever happens to it.

An ingest wraps its work in `recorded_run`. The work fills in what it learns
(the scope, the upstream date, how many rows) and may mark the run skipped.
On the way out exactly one `ingest_runs` row is written:

  * succeeded or skipped: in the same transaction as the data, so a row
    saying "succeeded" can never describe data that was not committed
  * failed: the data is rolled back first, then the failure row is written
    and committed on its own, and the exception is raised again so the
    caller (and the nightly GitHub Action) still fails visibly
"""

import datetime as dt
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import IngestRun

# Enough of a traceback to find the line, without filling the table.
MAX_ERROR_CHARS = 4000


@dataclass
class RunRecord:
    """What the work inside `recorded_run` reports about itself."""

    scope: str = ""
    source_url: str | None = None
    upstream_updated_at: dt.datetime | None = None
    row_count: int = 0
    notes: str | None = None
    status: str = "succeeded"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def describe(exc: BaseException) -> str:
    """The error first, then as much of the traceback as fits.

    The first line is what someone scanning the table needs ("RuntimeError:
    fdn has no pack contents yet"); the traceback below it is for finding the
    line. A long traceback loses its oldest frames, keeping the ones nearest
    the error.
    """
    summary = f"{type(exc).__name__}: {exc}"
    trace = "".join(traceback.format_exception(exc)).strip()
    room = MAX_ERROR_CHARS - len(summary) - 2
    if room <= 0:
        return summary[:MAX_ERROR_CHARS]
    if len(trace) > room:
        trace = "…" + trace[-(room - 1) :]
    return f"{summary}\n\n{trace}"


@contextmanager
def recorded_run(session: Session, source: str, scope: str = "") -> Iterator[RunRecord]:
    """Run an ingest step and leave exactly one `ingest_runs` row for it."""
    record = RunRecord(scope=scope)
    started = _now()

    def row(status: str, error: str | None = None) -> IngestRun:
        return IngestRun(
            source=source,
            scope=record.scope,
            started_at=started,
            finished_at=_now(),
            status=status,
            error=error,
            source_url=record.source_url,
            upstream_updated_at=record.upstream_updated_at,
            row_count=record.row_count if status == "succeeded" else 0,
            notes=record.notes,
        )

    try:
        yield record
    except BaseException as exc:
        session.rollback()
        session.add(row("failed", describe(exc)))
        session.commit()
        raise
    session.add(row(record.status))
    session.commit()
