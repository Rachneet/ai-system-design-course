import os
import tempfile
from uuid import uuid4

import httpx
import pgserver
import pytest
from alembic import command
from alembic.config import Config

from switchboard.app import create_app
from switchboard.config import Settings
from tests import mock_upstream

ADMIN = {"Authorization": "Bearer admin-test-token-0123456789"}


@pytest.fixture(scope="session")
def pg_uri():
    srv = pgserver.get_server(tempfile.mkdtemp(), cleanup_mode="stop")
    yield srv.get_uri()
    srv.cleanup()


def migrate(uri: str, schema: str, revision: str = "head", down: bool = False) -> None:
    os.environ["SWITCHBOARD_DATABASE_URL"] = uri
    os.environ["SWITCHBOARD_DB_SCHEMA"] = schema
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    (command.downgrade if down else command.upgrade)(cfg, revision)


@pytest.fixture
def schema(pg_uri):
    import psycopg

    name = f"t_{uuid4().hex[:10]}"
    with psycopg.connect(pg_uri, autocommit=True) as c:
        c.execute(f"CREATE SCHEMA {name}")
    migrate(pg_uri, name)
    yield name
    with psycopg.connect(pg_uri, autocommit=True) as c:
        c.execute(f"DROP SCHEMA {name} CASCADE")


@pytest.fixture
def upstream():
    mock_upstream.app.state.fail = {}
    mock_upstream.app.state.received = []
    mock_upstream.app.state.headers = []
    mock_upstream.app.state.delay_s = 0.0
    return mock_upstream.app


@pytest.fixture
async def gw(pg_uri, schema, upstream):
    cfg = Settings(
        database_url=pg_uri,
        db_schema=schema,
        admin_token=ADMIN["Authorization"][7:],
        anthropic_api_key="provider-secret",
        anthropic_base_url="http://upstream",
        allowed_beta_headers=["prompt-caching-2024-07-31"],
        breaker_threshold=3,
    )
    app = create_app(cfg, transport=httpx.ASGITransport(app=upstream))
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=transport, base_url="http://sb") as client:
        client.app = app
        yield client


async def provision(client, *, app_id="support-bot", team="cx", org="acme", **policy) -> str:
    """Create org, team, app and a key; return the plaintext key."""
    await client.post("/admin/orgs", json={"id": org, "name": org.title()}, headers=ADMIN)
    await client.post("/admin/teams", json={"id": team, "org_id": org, "name": team.upper()}, headers=ADMIN)
    r = await client.post("/admin/apps", json={"id": app_id, "team_id": team, "name": app_id} | policy, headers=ADMIN)
    assert r.status_code == 201, r.text
    r = await client.post(f"/admin/apps/{app_id}/keys", json={"label": "test"}, headers=ADMIN)
    return r.json()["key"]


def msg(model="claude-sonnet-5-5", text="hello", **extra) -> dict:
    return {"model": model, "max_tokens": 256, "messages": [{"role": "user", "content": text}]} | extra
