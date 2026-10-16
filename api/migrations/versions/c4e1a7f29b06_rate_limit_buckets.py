"""fetch_attempts becomes rate_limit_events, with a bucket column

Revision ID: c4e1a7f29b06
Revises: 9b3d7e1a4c52
Create Date: 2026-10-16 15:00:00.000000

ADR 0031 s6. The table began as the 17Lands fetch limit's counter. Deck
submissions then got their own allowance, first as a "deck:" prefix on the
client key, now as a `bucket` column ("fetch" or "deck"). The table is
renamed to match what it holds.

Existing rows are kept, since they are live allowances: a "deck:" row moves
to the deck bucket with the prefix taken off, and every other row is a
fetch.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c4e1a7f29b06"
down_revision: Union[str, Sequence[str], None] = "9b3d7e1a4c52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index("ix_fetch_attempts_client_attempted", table_name="fetch_attempts")
    op.rename_table("fetch_attempts", "rate_limit_events")
    # Renaming a table leaves its constraint and its id sequence with the
    # old name, so rename those too: the names should say what they belong to.
    op.execute(
        "ALTER TABLE rate_limit_events "
        "RENAME CONSTRAINT pk_fetch_attempts TO pk_rate_limit_events"
    )
    op.execute("ALTER SEQUENCE fetch_attempts_id_seq RENAME TO rate_limit_events_id_seq")

    # Added nullable, filled in, then made NOT NULL: a NOT NULL column can't
    # be added to a table that already has rows without a default.
    op.add_column("rate_limit_events", sa.Column("bucket", sa.String(16), nullable=True))
    op.execute(
        "UPDATE rate_limit_events SET bucket = 'deck', client = substr(client, 6) "
        "WHERE client LIKE 'deck:%'"
    )
    op.execute("UPDATE rate_limit_events SET bucket = 'fetch' WHERE bucket IS NULL")
    op.alter_column("rate_limit_events", "bucket", nullable=False)

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
    # Back to one allowance per key: deck rows get their prefix again.
    op.execute(
        "UPDATE rate_limit_events SET client = 'deck:' || client "
        "WHERE bucket = 'deck'"
    )
    op.drop_column("rate_limit_events", "bucket")
    op.execute("ALTER SEQUENCE rate_limit_events_id_seq RENAME TO fetch_attempts_id_seq")
    op.execute(
        "ALTER TABLE rate_limit_events "
        "RENAME CONSTRAINT pk_rate_limit_events TO pk_fetch_attempts"
    )
    op.rename_table("rate_limit_events", "fetch_attempts")
    op.create_index(
        "ix_fetch_attempts_client_attempted",
        "fetch_attempts",
        ["client", "created_at"],
        unique=False,
    )
