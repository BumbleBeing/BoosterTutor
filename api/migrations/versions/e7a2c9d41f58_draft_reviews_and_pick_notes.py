"""draft_reviews and pick_notes: Claude's stored prose about a draft

Revision ID: e7a2c9d41f58
Revises: c4e1a7f29b06
Create Date: 2026-10-16 18:00:00.000000

ADR 0031 s5, Phase 5d. Two new tables, so nothing to backfill. Only
admin-key calls write to them until Phase 6, so `user_id` is nullable for
now; Phase 6 deletes those rows and makes it NOT NULL.

The unique constraint is NULLS NOT DISTINCT (Postgres 15+; Supabase and CI
run 17), so the null "admin" owner gets one review per draft.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e7a2c9d41f58"
down_revision: Union[str, Sequence[str], None] = "c4e1a7f29b06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "draft_reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("draft_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "reviewed_deck", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "current_deck", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("summary_prompt_version", sa.String(length=32), nullable=True),
        sa.Column("summary_model", sa.String(length=64), nullable=True),
        sa.Column("summary_stats_snapshot", sa.DATE(), nullable=True),
        sa.ForeignKeyConstraint(
            ["draft_id"],
            ["drafts.draft_id"],
            name=op.f("fk_draft_reviews_draft_id_drafts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_draft_reviews")),
        sa.UniqueConstraint(
            "draft_id",
            "user_id",
            name="uq_draft_reviews_draft_id_user_id",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_table(
        "pick_notes",
        sa.Column("review_id", sa.UUID(), nullable=False),
        sa.Column("pack_number", sa.SmallInteger(), nullable=False),
        sa.Column("pick_number", sa.SmallInteger(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("stats_snapshot", sa.DATE(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["draft_reviews.id"],
            name=op.f("fk_pick_notes_review_id_draft_reviews"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "review_id", "pack_number", "pick_number", name=op.f("pk_pick_notes")
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("pick_notes")
    op.drop_table("draft_reviews")
