"""Tenants: an agent may belong to one tenant, and then acts only for users of that tenant. Approvals and decisions
carry the tenant so each tenant's approvers and dashboards see only their own.

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    op.execute("""
    ALTER TABLE agents ADD COLUMN tenant text;      -- NULL: not bound to a tenant (single-tenant deployments)
    ALTER TABLE approvals ADD COLUMN tenant text;
    ALTER TABLE decisions ADD COLUMN tenant text;
    CREATE INDEX decisions_tenant_ts ON decisions (tenant, ts);
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX decisions_tenant_ts;
    ALTER TABLE decisions DROP COLUMN tenant;
    ALTER TABLE approvals DROP COLUMN tenant;
    ALTER TABLE agents DROP COLUMN tenant;
    """)
