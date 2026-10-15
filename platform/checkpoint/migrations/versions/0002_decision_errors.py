"""Cedar evaluation errors in the decision log, so a deny caused by a broken condition says so.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.execute("ALTER TABLE decisions ADD COLUMN errors text[] NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE decisions DROP COLUMN errors")
