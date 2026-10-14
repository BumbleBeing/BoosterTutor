"""tax_value 12 -> 6 for HOB (ADR 0015)

Revision ID: c8f2a1b60d33
Revises: b1c7d4e9a20f
Create Date: 2026-09-22

The commitment tax is now summed per off-color rather than read off a pair
gap, so `tax_value` prices one whole off-color rather than a pair-overlap
fraction. The seeding migration is left untouched; this records the change
as its own step, which is also how ADR 0013 s4 says the value should move --
by hand, never by a job.

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c8f2a1b60d33"
down_revision: Union[str, Sequence[str], None] = "b1c7d4e9a20f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOTE = (
    "tax_value: hand-picked 2026-09-22, ADR 0015 -- 6.00 per off-color "
    "(was 12.00 per pair-overlap fraction under ADR 0012). Still no "
    "measurable basis; the three reference drafts cannot calibrate it"
)


def _set(tax: str, note: str) -> None:
    op.execute(
        sa.text(
            # The value travels as text, so cast it: Postgres will not put a
            # character varying into a numeric column on its own.
            "UPDATE format_constants SET tax_value = CAST(:tax AS numeric), updated_at = now(), "
            "source = regexp_replace(source, 'tax_value: .*$', :note) "
            "WHERE set_code = 'hob' AND event_type = 'PremierDraft'"
        ).bindparams(tax=tax, note=note)
    )


def upgrade() -> None:
    """Upgrade schema."""
    _set("6.00", NOTE)


def downgrade() -> None:
    """Downgrade schema."""
    _set("12.00", "tax_value: hand-picked 2026-09-21, ADR 0012 -- no measurable basis")
