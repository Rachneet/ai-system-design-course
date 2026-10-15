"""Alembic environment. Migrations are plain SQL (op.execute) so they read like the schema they create. They run as
the schema owner; the app connects as HELPDESK_APP_ROLE, which row-level security applies to."""

import os

from alembic import context
from sqlalchemy import create_engine, text

url = os.environ["HELPDESK_DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1)
schema = os.environ.get("HELPDESK_DB_SCHEMA")  # tests run each case in its own schema


def run() -> None:
    engine = create_engine(url)
    with engine.connect() as conn:
        if schema:
            conn.execute(text(f'SET search_path TO "{schema}", public'))
            conn.commit()
        context.configure(connection=conn, version_table_schema=schema)
        with context.begin_transaction():
            context.run_migrations()


run()
