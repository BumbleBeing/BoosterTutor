"""the booster_cards table

Revision ID: 7f4c2e8a915b
Revises: d2a9f6c41b87
Create Date: 2026-10-14 16:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "7f4c2e8a915b"
down_revision: Union[str, Sequence[str], None] = "d2a9f6c41b87"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "booster_cards",
        sa.Column("set_code", sa.String(length=8), nullable=False),
        sa.Column("oracle_id", sa.UUID(), nullable=False),
        sa.Column("sheet", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["oracle_id"],
            ["cards.oracle_id"],
            name=op.f("fk_booster_cards_oracle_id_cards"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["set_code"],
            ["sets.set_code"],
            name=op.f("fk_booster_cards_set_code_sets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("set_code", "oracle_id", name=op.f("pk_booster_cards")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("booster_cards")
