"""drafts (the Replay Cache) and fetch_attempts (the rate limit's counter)

Revision ID: 9b3d7e1a4c52
Revises: d8b2f4a6c193
Create Date: 2026-10-16 10:00:00.000000

ADR 0031 s5 and s6. Two new tables, so nothing to backfill.
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
        "fetch_attempts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("client", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fetch_attempts")),
    )
    op.create_index(
        "ix_fetch_attempts_client_attempted",
        "fetch_attempts",
        ["client", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_fetch_attempts_client_attempted", table_name="fetch_attempts")
    op.drop_table("fetch_attempts")
    op.drop_index(op.f("ix_drafts_set_code"), table_name="drafts")
    op.drop_table("drafts")
