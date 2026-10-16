"""drafts (the Replay Cache) and rate_limit_events (the rate limits' counter)

Revision ID: 9b3d7e1a4c52
Revises: d8b2f4a6c193
Create Date: 2026-10-16 10:00:00.000000

ADR 0031 s5 and s6. Two new tables, so nothing to backfill.

Edited in place on 2026-10-16, before it had been applied to any database
but CI's throwaway ones: the counter table was `fetch_attempts`, and gained
a `bucket` column (and its new name) when deck submissions got their own
allowance.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9b3d7e1a4c52"
down_revision: Union[str, Sequence[str], None] = "d8b2f4a6c193"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "drafts",
        sa.Column("draft_id", sa.String(length=64), nullable=False),
        sa.Column("set_code", sa.String(length=8), nullable=False),
        sa.Column("log", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "fetched_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("draft_id", name=op.f("pk_drafts")),
    )
    op.create_index(op.f("ix_drafts_set_code"), "drafts", ["set_code"], unique=False)

    op.create_table(
        "rate_limit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("bucket", sa.String(length=16), nullable=False),
        sa.Column("client", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rate_limit_events")),
    )
    op.create_index(
        "ix_rate_limit_events_bucket_client_created",
        "rate_limit_events",
        ["bucket", "client", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_rate_limit_events_bucket_client_created", table_name="rate_limit_events"
    )
    op.drop_table("rate_limit_events")
    op.drop_index(op.f("ix_drafts_set_code"), table_name="drafts")
    op.drop_table("drafts")
