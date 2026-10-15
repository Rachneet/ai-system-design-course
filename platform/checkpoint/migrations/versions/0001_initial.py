"""Initial schema: agent and approver identities, approvals for held calls, and the decision log.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE agents (
      id          text PRIMARY KEY,                       -- the <id> in ckp_<id>_<secret>; the Cedar principal
      role        text NOT NULL CHECK (role IN ('agent', 'approver')),
      token_hash  text NOT NULL,
      created_at  timestamptz NOT NULL DEFAULT now(),
      revoked_at  timestamptz
    );

    -- A call that policy holds for a person. Approval covers exactly this agent, user, tool and arguments, once.
    CREATE TABLE approvals (
      id           bigserial PRIMARY KEY,
      agent_id     text NOT NULL REFERENCES agents(id),
      user_id      text NOT NULL,
      tool         text NOT NULL,
      args         jsonb NOT NULL,
      args_digest  text NOT NULL,
      status       text NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'used')),
      policies     text[] NOT NULL DEFAULT '{}',
      requested_at timestamptz NOT NULL DEFAULT now(),
      decided_by   text,
      decided_at   timestamptz,
      note         text,
      used_at      timestamptz
    );
    CREATE INDEX approvals_pending ON approvals (status, requested_at) WHERE status = 'pending';

    CREATE TABLE decisions (
      id          bigserial PRIMARY KEY,
      ts          timestamptz NOT NULL DEFAULT now(),
      agent_id    text NOT NULL,
      user_id     text,
      action      text NOT NULL,
      tool        text NOT NULL,
      decision    text NOT NULL,                          -- allow | deny | hold | approved | rate_limited | error
      policies    text[] NOT NULL DEFAULT '{}',
      flags       text[] NOT NULL DEFAULT '{}',
      latency_ms  integer
    );
    CREATE INDEX decisions_ts ON decisions (ts);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE decisions, approvals, agents")
