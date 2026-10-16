"""card_mana_sources: each set's Fixers

Revision ID: a6c4e2b81d57
Revises: f3b8d2c71e04
Create Date: 2026-10-15 23:30:00.000000

ADR 0028 s1: loaded from the taxonomy file's `mana_sources` section, with
each entry's weights already resolved. A new table, so nothing to backfill.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a6c4e2b81d57"
down_revision: Union[str, Sequence[str], None] = "f3b8d2c71e04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "card_mana_sources",
        sa.Column("set_code", sa.String(length=8), nullable=False),
        sa.Column("oracle_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("colors", sa.String(length=8), nullable=False),
        sa.Column("expected", sa.Float(), nullable=True),
        sa.Column("color_weight", sa.Float(), nullable=False),
        sa.Column("land_weight", sa.Float(), nullable=False),
        sa.Column("min_mana_value", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "color_weight >= 0 AND land_weight >= 0 AND min_mana_value >= 0",
            name=op.f("ck_card_mana_sources_weights_not_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["oracle_id"],
            ["cards.oracle_id"],
            name=op.f("fk_card_mana_sources_oracle_id_cards"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "set_code", "oracle_id", name=op.f("pk_card_mana_sources")
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("card_mana_sources")
