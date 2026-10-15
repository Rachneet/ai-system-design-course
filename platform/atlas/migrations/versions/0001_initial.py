"""Initial schema: teams, principals, versioned artifacts with their findings, and the audit log.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE teams (
      id          text PRIMARY KEY,
      name        text NOT NULL,
      created_at  timestamptz NOT NULL DEFAULT now()
    );

    CREATE TABLE principals (
      id          text PRIMARY KEY,                      -- the <id> in atk_<id>_<secret>
      label       text NOT NULL,
      team_id     text REFERENCES teams(id),             -- publishers act for one team
      roles       text[] NOT NULL,
      token_hash  text NOT NULL,                         -- sha256 of the secret; the token is shown once
      created_at  timestamptz NOT NULL DEFAULT now(),
      revoked_at  timestamptz
    );

    -- array_to_string is only STABLE, so generated columns cannot call it; joining text is deterministic.
    CREATE FUNCTION atlas_tags_text(text[]) RETURNS text
      LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT array_to_string($1, ' ') $$;

    -- One row per published version. A version's content never changes; a fix is a new version.
    CREATE TABLE artifacts (
      id            bigserial PRIMARY KEY,
      kind          text NOT NULL CHECK (kind IN ('mcp_server', 'a2a_agent', 'skill')),
      name          text NOT NULL,
      version       text NOT NULL,
      team_id       text REFERENCES teams(id),           -- owner; NULL for upstream imports until adopted
      status        text NOT NULL CHECK (status IN ('in_review', 'approved', 'rejected', 'deprecated')),
      source        text NOT NULL DEFAULT 'internal' CHECK (source IN ('internal', 'upstream')),
      title         text NOT NULL,
      description   text NOT NULL,
      tags          text[] NOT NULL DEFAULT '{}',
      license       text,
      document      jsonb NOT NULL,                      -- server.json, the agent card, or skill frontmatter
      digest        text NOT NULL,                       -- sha256 of the canonical document or the package bytes
      package       bytea,                               -- skill zips only
      eval          jsonb,                               -- optional eval report: {suite, score, url}
      submitted_by  text NOT NULL,
      reviewed_by   text,
      reviewed_at   timestamptz,
      review_note   text,
      created_at    timestamptz NOT NULL DEFAULT now(),
      search        tsvector GENERATED ALWAYS AS (
                      setweight(to_tsvector('simple', coalesce(name, '')), 'A') ||
                      setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                      setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
                      setweight(to_tsvector('simple', atlas_tags_text(tags)), 'C')
                    ) STORED,
      UNIQUE (kind, name, version)
    );
    CREATE INDEX artifacts_search ON artifacts USING gin (search);
    CREATE INDEX artifacts_kind_status ON artifacts (kind, status, name);

    CREATE TABLE findings (
      artifact_id  bigint NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
      check_name   text NOT NULL,
      severity     text NOT NULL CHECK (severity IN ('block', 'warn', 'info')),
      message      text NOT NULL,
      location     text NOT NULL DEFAULT ''
    );
    CREATE INDEX findings_artifact ON findings (artifact_id);

    CREATE TABLE audit (
      id       bigserial PRIMARY KEY,
      ts       timestamptz NOT NULL DEFAULT now(),
      actor    text NOT NULL,
      action   text NOT NULL,
      target   text NOT NULL,
      details  jsonb NOT NULL DEFAULT '{}'
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE audit, findings, artifacts, principals, teams; DROP FUNCTION atlas_tags_text(text[])")
