"""deck_rating_models: each format's fitted Deck Ratings

Revision ID: c3f7a9d5e218
Revises: a6c4e2b81d57
Create Date: 2026-10-16 00:30:00.000000

ADR 0026 s2: the logistic regression and percentile tables, fitted from the
game dump by the deck-ratings ingest. A new table, so nothing to backfill.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3f7a9d5e218"
down_revision: Union[str, Sequence[str], None] = "a6c4e2b81d57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "deck_rating_models",
        sa.Column("set_code", sa.String(length=8), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("decks", sa.Integer(), nullable=False),
        sa.Column("games", sa.Integer(), nullable=False),
        sa.Column("intercept", sa.Float(), nullable=False),
        sa.Column("coefficients", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("standard_errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quantiles", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "fitted_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "set_code", "event_type", "snapshot_date", name=op.f("pk_deck_rating_models")
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("deck_rating_models")
