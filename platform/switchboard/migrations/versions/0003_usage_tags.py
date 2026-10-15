"""A caller-supplied tag on each ledger row (x-switchboard-tag), so cost can be joined to a unit of work such as a
support ticket.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE usage_events ADD COLUMN tag text;
    CREATE INDEX usage_events_tag ON usage_events (tag, ts) WHERE tag IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX usage_events_tag; ALTER TABLE usage_events DROP COLUMN tag")
