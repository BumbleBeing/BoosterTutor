"""Every ingest run leaves exactly one `ingest_runs` row, whatever happens.

`recorded_run` is exercised against a stand-in session that only remembers
what was added, committed and rolled back: the point is the order of those
calls, which a real database would hide.
"""

from typing import Any

import pytest

from boostertutor.ingest.runs import MAX_ERROR_CHARS, describe, recorded_run
from boostertutor.models import Base, IngestRun


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.calls.append("add")
        self.added.append(obj)

    def commit(self) -> None:
        self.calls.append("commit")

    def rollback(self) -> None:
        self.calls.append("rollback")


def test_a_successful_run_is_recorded_with_its_data_in_one_commit() -> None:
    session = FakeSession()
    with recorded_run(session, "17lands", "hob:PremierDraft") as record:  # type: ignore[arg-type]
        record.row_count = 42
        record.notes = "snapshot 2026-10-01"
    assert session.calls == ["add", "commit"]
    (run,) = session.added
    assert (run.source, run.scope, run.status, run.row_count, run.error) == (
        "17lands",
        "hob:PremierDraft",
        "succeeded",
        42,
        None,
    )
    assert run.started_at <= run.finished_at


def test_a_skipped_run_is_recorded_as_skipped() -> None:
    session = FakeSession()
    with recorded_run(session, "scryfall") as record:  # type: ignore[arg-type]
        record.scope = "fra,hob,msh"
        record.status = "skipped"
    (run,) = session.added
    assert (run.status, run.scope) == ("skipped", "fra,hob,msh")


def test_a_failure_rolls_back_records_the_error_and_still_raises() -> None:
    session = FakeSession()
    with (
        pytest.raises(ValueError, match="bad dump"),
        recorded_run(session, "17lands", "msh:PremierDraft") as record,
    ):  # type: ignore[arg-type]
        record.row_count = 99  # written before the failure; must not be claimed
        raise ValueError("bad dump")
    assert session.calls == ["rollback", "add", "commit"]
    (run,) = session.added
    assert run.status == "failed"
    assert run.row_count == 0
    assert "ValueError: bad dump" in run.error


def test_the_error_comes_first_and_the_traceback_is_trimmed_to_fit() -> None:
    try:
        raise RuntimeError("fdn has no pack contents yet")
    except RuntimeError as exc:
        short = describe(exc)
    assert short.startswith("RuntimeError: fdn has no pack contents yet\n\nTraceback")

    try:
        raise RuntimeError("x" * (MAX_ERROR_CHARS * 2))
    except RuntimeError as exc:
        long = describe(exc)
    assert len(long) <= MAX_ERROR_CHARS
    assert long.startswith("RuntimeError: xxx")


def test_ingest_runs_record_status_timing_and_error() -> None:
    columns = set(Base.metadata.tables["ingest_runs"].columns.keys())
    assert {"started_at", "finished_at", "status", "error"} <= columns
    assert "ran_at" not in columns
    assert IngestRun.__table__.c.status.index
