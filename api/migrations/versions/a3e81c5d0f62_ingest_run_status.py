"""ingest_runs: start and finish times, status, and error

Revision ID: a3e81c5d0f62
Revises: 05f455461526
Create Date: 2026-10-15 02:00:00.000000

Development plan 2.4 asks the table to log failures too. Every run now leaves
a row: succeeded, skipped (upstream unchanged), or failed with its error.
`ran_at` becomes `started_at`, renamed rather than dropped so the existing
rows keep their history; they were all successful runs, and are backfilled
as such.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a3e81c5d0f62"
down_revision: Union[str, Sequence[str], None] = "05f455461526"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("ingest_runs", "ran_at", new_column_name="started_at", server_default=None)
    op.add_column("ingest_runs", sa.Column("finished_at", postgresql.TIMESTAMP(timezone=True), nullable=True))
    # The default exists only to fill the existing rows; the code always sets it.
    op.add_column(
        "ingest_runs",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="succeeded"),
    )
    op.alter_column("ingest_runs", "status", server_default=None)
    op.add_column("ingest_runs", sa.Column("error", sa.Text(), nullable=True))
    op.execute("UPDATE ingest_runs SET finished_at = started_at")
    op.create_index(op.f("ix_ingest_runs_status"), "ingest_runs", ["status"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_ingest_runs_status"), table_name="ingest_runs")
    # Failed and skipped runs had no place in the old shape.
    op.execute("DELETE FROM ingest_runs WHERE status <> 'succeeded'")
    op.drop_column("ingest_runs", "error")
    op.drop_column("ingest_runs", "status")
    op.drop_column("ingest_runs", "finished_at")
    op.alter_column(
        "ingest_runs", "started_at", new_column_name="ran_at", server_default=sa.text("now()")
    )
