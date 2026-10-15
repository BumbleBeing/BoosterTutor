"""A record of every ingest run: what was fetched, from where, and how fresh it was.

Three jobs. It lets an ingest skip work when the upstream file has not
changed since the last successful run (development plan 2.2, step 5); the
nightly GitHub Action keeps no files between runs, so the database is the
only place that memory can live. It is the provenance a reader of the data
needs: "these win rates come from the 17Lands dump of such-and-such a date".
And it is the log that says when the data went stale and why (plan 2.4):
every run leaves a row, including the ones that found nothing to do and the
ones that failed.
"""

import datetime as dt

from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    # Which ingest: "scryfall" or "17lands".
    source: Mapped[str] = mapped_column(String(32), index=True)
    started_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # "succeeded": data written. "skipped": upstream unchanged, nothing to do.
    # "failed": nothing written; `error` says why. Only a succeeded run counts
    # when deciding whether the next one can skip.
    status: Mapped[str] = mapped_column(String(16), index=True)
    error: Mapped[str | None] = mapped_column(Text())
    source_url: Mapped[str | None] = mapped_column(Text())
    # When upstream says the data was last updated (Scryfall's bulk
    # `updated_at`). Null when upstream does not say.
    upstream_updated_at: Mapped[dt.datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    # What the run covered, e.g. the comma-joined set codes. A run is only
    # skippable if the same scope was ingested from the same upstream file.
    scope: Mapped[str] = mapped_column(String(256), default="")
    row_count: Mapped[int] = mapped_column(Integer(), default=0)
    notes: Mapped[str | None] = mapped_column(Text())
