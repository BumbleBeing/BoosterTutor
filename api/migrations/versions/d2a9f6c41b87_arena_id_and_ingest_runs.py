"""card_prints.arena_id, and the ingest_runs table

Revision ID: d2a9f6c41b87
Revises: c8f2a1b60d33
Create Date: 2026-10-14 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d2a9f6c41b87"
down_revision: Union[str, Sequence[str], None] = "c8f2a1b60d33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("card_prints", sa.Column("arena_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_card_prints_arena_id"), "card_prints", ["arena_id"], unique=False)

    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "ran_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("upstream_updated_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("scope", sa.String(length=256), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingest_runs")),
    )
    op.create_index(op.f("ix_ingest_runs_source"), "ingest_runs", ["source"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_ingest_runs_source"), table_name="ingest_runs")
    op.drop_table("ingest_runs")
    op.drop_index(op.f("ix_card_prints_arena_id"), table_name="card_prints")
    op.drop_column("card_prints", "arena_id")
