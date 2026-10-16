"""format_constants: per-format land targets (ADR 0028 s4)

Revision ID: d8b2f4a6c193
Revises: c3f7a9d5e218
Create Date: 2026-10-16 02:00:00.000000

The effective land count's targets move from code into each format's row.
HOB's values were measured by scripts/derive_land_targets.py on
game_data_public.HOB.PremierDraft.20261001: 16 lands below an average mana
value of 3.0 and 18 from 3.0, with no 17 band. Every existing row is HOB's,
so the columns are added nullable, filled, then made required.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d8b2f4a6c193"
down_revision: Union[str, Sequence[str], None] = "c3f7a9d5e218"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = {
    "land_target_low": sa.Integer(),
    "land_target_mid": sa.Integer(),
    "land_target_high": sa.Integer(),
    "land_low_below_mv": sa.Numeric(precision=4, scale=2),
    "land_high_from_mv": sa.Numeric(precision=4, scale=2),
}

NOTE = (
    "; land targets: measured 2026-10-15 by scripts/derive_land_targets.py, "
    "ADR 0028 s4 -- 16 below 3.0 average MV, 18 from 3.0, no 17 band"
)


def upgrade() -> None:
    """Upgrade schema."""
    for name, type_ in COLUMNS.items():
        op.add_column("format_constants", sa.Column(name, type_, nullable=True))
    op.execute(
        sa.text(
            "UPDATE format_constants SET land_target_low = 16, land_target_mid = 17, "
            "land_target_high = 18, land_low_below_mv = 3.00, land_high_from_mv = 3.00, "
            "source = source || :note, updated_at = now() "
            "WHERE set_code = 'hob' AND event_type = 'PremierDraft'"
        ).bindparams(note=NOTE)
    )
    for name in COLUMNS:
        op.alter_column("format_constants", name, nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        sa.text(
            "UPDATE format_constants SET source = replace(source, :note, '') "
            "WHERE set_code = 'hob' AND event_type = 'PremierDraft'"
        ).bindparams(note=NOTE)
    )
    for name in reversed(list(COLUMNS)):
        op.drop_column("format_constants", name)
