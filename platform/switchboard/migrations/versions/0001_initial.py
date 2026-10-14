"""Initial schema: tenancy, keys, limits, usage ledger, spend, audit.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE orgs (
      id               text PRIMARY KEY,
      name             text NOT NULL,
      budget_usd_month numeric(12, 2),                -- NULL = no limit at this level
      created_at       timestamptz NOT NULL DEFAULT now()
    );

    CREATE TABLE teams (
      id               text PRIMARY KEY,
      org_id           text NOT NULL REFERENCES orgs(id),
      name             text NOT NULL,
      budget_usd_month numeric(12, 2),
      created_at       timestamptz NOT NULL DEFAULT now()
    );

    CREATE TABLE apps (
      id               text PRIMARY KEY,
      team_id          text NOT NULL REFERENCES teams(id),
      name             text NOT NULL,
      allowed_models   text[] NOT NULL DEFAULT '{}',  -- empty = every priced model
      rpm              int NOT NULL DEFAULT 60,
      tpm              int NOT NULL DEFAULT 200000,
      budget_usd_month numeric(12, 2),
      pii_mode         text NOT NULL DEFAULT 'detect' CHECK (pii_mode IN ('off', 'detect', 'redact')),
      log_bodies       boolean NOT NULL DEFAULT false,
      retention_days   int NOT NULL DEFAULT 30 CHECK (retention_days BETWEEN 1 AND 400),
      created_at       timestamptz NOT NULL DEFAULT now()
    );

    CREATE TABLE api_keys (
      id           text PRIMARY KEY,                  -- public id, also the visible prefix: sbk_<id>_<secret>
      app_id       text NOT NULL REFERENCES apps(id),
      secret_hash  text NOT NULL,                     -- sha256 of the whole key; the key itself is never stored
      label        text,
      created_at   timestamptz NOT NULL DEFAULT now(),
      expires_at   timestamptz,
      revoked_at   timestamptz,
      last_used_at timestamptz
    );
    CREATE INDEX api_keys_app ON api_keys (app_id);

    CREATE TABLE buckets (
      key          text PRIMARY KEY,                  -- 'rpm:<app>' or 'tpm:<app>'
      tokens       double precision NOT NULL,
      last_allowed boolean NOT NULL DEFAULT true,
      updated_at   timestamptz NOT NULL DEFAULT now()
    );

    -- Append-only: the source of truth for usage, cost, and chargeback.
    CREATE TABLE usage_events (
      id             bigserial PRIMARY KEY,
      request_id     text NOT NULL UNIQUE,
      ts             timestamptz NOT NULL DEFAULT now(),
      key_id         text NOT NULL,
      app_id         text NOT NULL,
      team_id        text NOT NULL,
      org_id         text NOT NULL,
      requested_model text NOT NULL,
      served_model   text,
      fallback       boolean NOT NULL DEFAULT false,
      status         int NOT NULL,
      stream         boolean NOT NULL,
      input_tokens   int NOT NULL DEFAULT 0,
      output_tokens  int NOT NULL DEFAULT 0,
      cache_read_tokens  int NOT NULL DEFAULT 0,
      cache_write_tokens int NOT NULL DEFAULT 0,
      cost_usd       numeric(14, 8) NOT NULL DEFAULT 0,
      latency_ms     int NOT NULL,
      ttfb_ms        int,
      pii_findings   int NOT NULL DEFAULT 0,
      error_type     text
    );
    CREATE INDEX usage_events_team_ts ON usage_events (team_id, ts);
    CREATE INDEX usage_events_app_ts ON usage_events (app_id, ts);

    -- Running monthly totals per scope, updated in the same transaction as the ledger row.
    CREATE TABLE spend_monthly (
      scope    text NOT NULL CHECK (scope IN ('org', 'team', 'app')),
      scope_id text NOT NULL,
      month    date NOT NULL,
      cost_usd numeric(14, 8) NOT NULL DEFAULT 0,
      requests bigint NOT NULL DEFAULT 0,
      PRIMARY KEY (scope, scope_id, month)
    );

    -- Opt-in, redacted request and response bodies with a hard expiry.
    CREATE TABLE audit_bodies (
      request_id  text PRIMARY KEY REFERENCES usage_events(request_id) ON DELETE CASCADE,
      app_id      text NOT NULL,
      request     jsonb NOT NULL,
      response    text,
      expires_at  timestamptz NOT NULL
    );
    CREATE INDEX audit_bodies_expiry ON audit_bodies (expires_at);

    -- Who changed what in the control plane.
    CREATE TABLE admin_audit (
      id      bigserial PRIMARY KEY,
      ts      timestamptz NOT NULL DEFAULT now(),
      actor   text NOT NULL,
      action  text NOT NULL,
      target  text NOT NULL,
      details jsonb NOT NULL DEFAULT '{}'
    );
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE admin_audit, audit_bodies, spend_monthly, usage_events, buckets, api_keys, apps, teams, orgs;
    """)
