"""Instance heartbeats, used to split per-app rate limits across live gateway instances.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.execute("""
    CREATE TABLE instances (
      id        text PRIMARY KEY,
      last_seen timestamptz NOT NULL DEFAULT now()
    );
    DROP TABLE buckets;  -- shared buckets were a hot row under load (see ADR 0002)
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE instances;
    CREATE TABLE buckets (
      key text PRIMARY KEY, tokens double precision NOT NULL, last_allowed boolean NOT NULL DEFAULT true,
      updated_at timestamptz NOT NULL DEFAULT now()
    );
    """)
