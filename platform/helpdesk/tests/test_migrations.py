import os

from alembic import command
from alembic.config import Config

from tests.harness import HERE, schema


def test_migrations_round_trip(pg_uri):
    name = schema(pg_uri)
    os.environ.update(HELPDESK_DATABASE_URL=pg_uri, HELPDESK_DB_SCHEMA=name, HELPDESK_APP_ROLE="helpdesk_app")
    cfg = Config(str(HERE / "alembic.ini"))
    cfg.set_main_option("script_location", str(HERE / "migrations"))
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
