"""Approvals expire: a pending request lapses if nobody decides in time, and an approval must be used soon after
it is granted. Lapsed rows become 'expired' and can never be used.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE approvals ADD COLUMN expires_at timestamptz;
    -- Requests open during the upgrade get a grace window rather than lapsing at once.
    UPDATE approvals SET expires_at = CASE WHEN status IN ('pending', 'approved') THEN now() + interval '30 minutes'
                                           ELSE coalesce(used_at, decided_at, requested_at) END;
    ALTER TABLE approvals ALTER COLUMN expires_at SET NOT NULL;
    ALTER TABLE approvals DROP CONSTRAINT approvals_status_check;
    ALTER TABLE approvals ADD CONSTRAINT approvals_status_check
      CHECK (status IN ('pending', 'approved', 'rejected', 'used', 'expired'));
    CREATE INDEX approvals_open ON approvals (expires_at) WHERE status IN ('pending', 'approved');
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX approvals_open;
    UPDATE approvals SET status = 'rejected' WHERE status = 'expired';
    ALTER TABLE approvals DROP CONSTRAINT approvals_status_check;
    ALTER TABLE approvals ADD CONSTRAINT approvals_status_check
      CHECK (status IN ('pending', 'approved', 'rejected', 'used'));
    ALTER TABLE approvals DROP COLUMN expires_at;
    """)
