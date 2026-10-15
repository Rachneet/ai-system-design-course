"""Pinned tool lists for MCP servers: the tools/list result a reviewer approved, and its digest, which gateways
compare with what the server returns at run time.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE artifacts ADD COLUMN tools jsonb;          -- MCP servers only; NULL when no tool list was submitted
    ALTER TABLE artifacts ADD COLUMN tools_digest text;    -- sha256 of the canonical tool list
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE artifacts DROP COLUMN tools_digest, DROP COLUMN tools")
