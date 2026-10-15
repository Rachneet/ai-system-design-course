import io
import json
import os
import tempfile
import zipfile
from uuid import uuid4

import httpx
import pgserver
import pytest
from alembic import command
from alembic.config import Config

from atlas.app import create_app
from atlas.config import Settings
from tests import mock_registry

ADMIN = {"Authorization": "Bearer admin-test-token-0123456789"}


@pytest.fixture(scope="session")
def pg_uri():
    srv = pgserver.get_server(tempfile.mkdtemp(), cleanup_mode="stop")
    yield srv.get_uri()
    srv.cleanup()


def migrate(uri: str, schema: str, revision: str = "head", down: bool = False) -> None:
    os.environ["ATLAS_DATABASE_URL"] = uri
    os.environ["ATLAS_DB_SCHEMA"] = schema
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


def settings(pg_uri, schema, **over) -> Settings:
    return Settings(database_url=pg_uri, db_schema=schema, admin_token=ADMIN["Authorization"][7:], **over)


@pytest.fixture
async def client(pg_uri, schema):
    async with make_client(settings(pg_uri, schema)) as c:
        yield c


class make_client:
    def __init__(self, cfg: Settings):
        self.app = create_app(cfg, upstream_transport=httpx.ASGITransport(app=mock_registry.app))

    async def __aenter__(self):
        self.ctx = self.app.router.lifespan_context(self.app)
        await self.ctx.__aenter__()
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://atlas")
        self.http.app = self.app
        return self.http

    async def __aexit__(self, *exc):
        await self.http.aclose()
        await self.ctx.__aexit__(*exc)


async def token(client, roles: list[str], team: str | None = "payments") -> dict:
    if team:
        await client.post("/admin/teams", json={"id": team, "name": team.title()}, headers=ADMIN)
    r = await client.post(
        "/admin/principals", json={"label": f"{'-'.join(roles)}@{team}", "team_id": team, "roles": roles}, headers=ADMIN
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def server(name="io.github.acme/weather", version="1.0.0", **extra) -> dict:
    return {
        "name": name,
        "description": "Weather forecasts for agents",
        "version": version,
        "remotes": [{"type": "streamable-http", "url": "https://mcp.acme.example/weather"}],
        "repository": {"url": "https://github.com/acme/weather-mcp", "source": "github"},
    } | extra


def card(version="1.0.0", **extra) -> dict:
    return {
        "name": "Refund Agent",
        "description": "Checks refund eligibility and drafts the refund for approval",
        "version": version,
        "supportedInterfaces": [
            {"url": "https://agents.acme.example/refunds", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
        ],
        "capabilities": {"streaming": True},
        "securitySchemes": {"oauth": {"type": "oauth2"}},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [{"id": "refund-check", "name": "Refund check", "description": "Eligibility", "tags": ["refunds"]}],
    } | extra


def skill_zip(name="pdf-forms", description="Fill PDF forms. Use when the user has a PDF form.", files=None, **meta):
    front = {"name": name, "description": description, "license": "MIT"} | meta
    head = "---\n" + "".join(f"{k}: {json.dumps(v)}\n" for k, v in front.items() if v is not None) + "---\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{name}/SKILL.md", head + "# Fill forms\n\nRun scripts/fill.py.\n")
        for path, data in (files or {}).items():
            z.writestr(path, data)
    return buf.getvalue()
