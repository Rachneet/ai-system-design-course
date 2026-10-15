"""Initial schema: tickets and their transcript, the trace of every model and tool call, escalations, calls held for
approval, per-agent kill switches and purge runs. Tenant-owned tables are isolated by row-level security.

Revision ID: 0001
Revises:
"""

import os
import re

from alembic import op

revision = "0001"
down_revision = None
TENANT_TABLES = ("tickets", "messages", "events", "escalations", "pending_calls")


def upgrade() -> None:
    op.execute("""
    CREATE TABLE tickets (
      id           text PRIMARY KEY,                     -- T-<random>; never chosen by a client
      tenant       text NOT NULL,
      user_id      text NOT NULL,                        -- the JWT sub of the person who opened it
      status       text NOT NULL CHECK (status IN ('open', 'waiting_approval', 'escalated', 'answered', 'resolved')),
      agent_id     text NOT NULL,                        -- the agent that owns it now
      handoffs     int NOT NULL DEFAULT 0,
      trace_id     text NOT NULL,                        -- one W3C trace per ticket, across every service
      resolved_by  text,                                 -- an agent id, or 'human'
      created_at   timestamptz NOT NULL DEFAULT now(),
      updated_at   timestamptz NOT NULL DEFAULT now(),
      resolved_at  timestamptz,
      reopened_at  timestamptz                           -- set when the user writes again within the reopen window
    );
    CREATE INDEX tickets_tenant_user ON tickets (tenant, user_id, created_at);

    -- The transcript in chat-completions shape. Each agent sees user messages and its own turns, not other agents'.
    CREATE TABLE messages (
      id           bigserial PRIMARY KEY,
      ticket_id    text NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
      tenant       text NOT NULL,
      role         text NOT NULL CHECK (role IN ('user', 'assistant', 'tool', 'system')),
      agent_id     text,
      content      text,
      tool_calls   jsonb,
      tool_call_id text,
      created_at   timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX messages_ticket ON messages (ticket_id, id);

    -- The trace: every model call (with Switchboard's request id), tool call (with Checkpoint's outcome), handoff,
    -- escalation, approval and switch, so one query reconstructs a ticket from start to end.
    CREATE TABLE events (
      id           bigserial PRIMARY KEY,
      ticket_id    text REFERENCES tickets(id) ON DELETE CASCADE,
      tenant       text NOT NULL,
      ts           timestamptz NOT NULL DEFAULT now(),
      kind         text NOT NULL CHECK (kind IN ('model_call', 'tool_call', 'handoff', 'escalation', 'approval',
                                                 'resolution', 'switch', 'reply')),
      agent_id     text,
      detail       jsonb NOT NULL DEFAULT '{}'
    );
    CREATE INDEX events_ticket ON events (ticket_id, id);
    CREATE INDEX events_tenant_ts ON events (tenant, ts);

    CREATE TABLE escalations (
      id           bigserial PRIMARY KEY,
      ticket_id    text NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
      tenant       text NOT NULL,
      agent_id     text,
      reason       text NOT NULL,
      summary      text NOT NULL,
      status       text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
      created_at   timestamptz NOT NULL DEFAULT now(),
      resolved_by  text,
      resolved_at  timestamptz,
      note         text
    );
    CREATE INDEX escalations_open ON escalations (tenant, created_at) WHERE status = 'open';

    -- A tool call Checkpoint held for approval, kept so it runs once, with exactly the approved arguments.
    CREATE TABLE pending_calls (
      ticket_id    text PRIMARY KEY REFERENCES tickets(id) ON DELETE CASCADE,
      tenant       text NOT NULL,
      agent_id     text NOT NULL,
      approval_id  bigint NOT NULL,
      tool         text NOT NULL,
      args         jsonb NOT NULL,
      tool_call_id text NOT NULL,
      user_token   text NOT NULL,                        -- the requester's JWT, to run the call once approved (ADR 0002);
                                                         -- deleted when used, useless after its exp
      created_at   timestamptz NOT NULL DEFAULT now()
    );
    CREATE UNIQUE INDEX pending_calls_approval ON pending_calls (tenant, approval_id);

    -- Kill switches. Not tenant-isolated: an agent belongs to one tenant, and supervisors are checked in the API.
    CREATE TABLE agent_switches (
      agent_id     text PRIMARY KEY,
      enabled      boolean NOT NULL,
      reason       text NOT NULL,
      changed_by   text NOT NULL,
      changed_at   timestamptz NOT NULL DEFAULT now()
    );

    CREATE TABLE purge_runs (
      id           bigserial PRIMARY KEY,
      ts           timestamptz NOT NULL DEFAULT now(),
      tenant       text NOT NULL,
      table_name   text NOT NULL,
      older_than_days int NOT NULL,
      deleted      int NOT NULL
    );
    """)
    for table in TENANT_TABLES:
        op.execute(f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON {table}
          USING (tenant = current_setting('helpdesk.tenant', true))
          WITH CHECK (tenant = current_setting('helpdesk.tenant', true));
        """)
    role = os.environ.get("HELPDESK_APP_ROLE", "helpdesk_app")
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role):
        raise ValueError("HELPDESK_APP_ROLE must be a plain lowercase role name")
    op.execute(f"""
    DO $$ BEGIN
      IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
        EXECUTE format('GRANT USAGE ON SCHEMA %I TO {role}', current_schema());
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO {role}', current_schema());
        EXECUTE format('GRANT USAGE ON ALL SEQUENCES IN SCHEMA %I TO {role}', current_schema());
      END IF;
    END $$;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE purge_runs, agent_switches, pending_calls, escalations, events, messages, tickets")
