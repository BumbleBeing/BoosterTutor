"""A record of every ingest run: what was fetched, from where, and how fresh it was.

Two jobs. It lets an ingest skip work when the upstream file has not changed
since the last successful run (development plan 2.2, step 5); the nightly
GitHub Action keeps no files between runs, so the database is the only place
that memory can live. And it is the provenance a reader of the data needs:
"these win rates come from the 17Lands dump of such-and-such a date".
"""

import datetime as dt

from sqlalchemy import Integer, String, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    # Which ingest: "scryfall" now, the 17Lands sources later.
    source: Mapped[str] = mapped_column(String(32), index=True)
    ran_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
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
