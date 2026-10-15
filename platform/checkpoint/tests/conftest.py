import os
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
import jwt
import pgserver
import pytest
from alembic import command
from alembic.config import Config

from checkpoint.app import create_app
from checkpoint.config import Settings
from tests import mock_servers

ADMIN = {"Authorization": "Bearer admin-test-token-0123456789"}
USER_SECRET = "user-jwt-secret-for-tests-0123456789"
POLICY = (Path(__file__).parent.parent / "policies" / "default.cedar").read_text()


@pytest.fixture(scope="session")
def pg_uri():
    srv = pgserver.get_server(tempfile.mkdtemp(), cleanup_mode="stop")
    yield srv.get_uri()
    srv.cleanup()


def migrate(uri, schema, revision="head", down=False):
    os.environ["CHECKPOINT_DATABASE_URL"] = uri
    os.environ["CHECKPOINT_DB_SCHEMA"] = schema
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


def settings(pg_uri, schema, **over):
    return Settings(
        database_url=pg_uri,
        db_schema=schema,
        admin_token=ADMIN["Authorization"][7:],
        atlas_url="https://atlas.example",
        user_jwt_secret=USER_SECRET,
        upstream_credentials={"com.acme/payments": "Bearer payments-service-credential"},
        **over,
    )


class Gateway:
    def __init__(self, cfg, policy=POLICY):
        mock_servers.seen.clear()
        mock_servers.state.update(sessions=set(), initializes=0)
        t = httpx.ASGITransport(app=mock_servers.app)
        self.app = create_app(cfg, atlas_transport=t, upstream_transport=t, policy_text=policy)

    async def __aenter__(self):
        self.ctx = self.app.router.lifespan_context(self.app)
        await self.ctx.__aenter__()
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://checkpoint")
        self.http.app = self.app
        return self.http

    async def __aexit__(self, *exc):
        await self.http.aclose()
        await self.ctx.__aexit__(*exc)


@pytest.fixture
async def gw(pg_uri, schema):
    async with Gateway(settings(pg_uri, schema)) as c:
        yield c


async def agent(client, agent_id="refunds", role="agent") -> dict:
    r = await client.post("/admin/agents", json={"id": agent_id, "role": role}, headers=ADMIN)
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def user_token(sub="u1", roles=("support",), secret=USER_SECRET) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": sub, "roles": list(roles), "aud": "checkpoint", "iat": now, "exp": now + 300}, secret, "HS256"
    )


_rid = iter(range(1, 10_000))


def rpc(method, params=None, meta=None):
    """A well-formed 2026-07-28 request and its mirrored headers."""
    params = dict(params or {})
    params["_meta"] = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {},
    } | (meta or {})
    body = {"jsonrpc": "2.0", "id": next(_rid), "method": method, "params": params}
    headers = {"mcp-protocol-version": "2026-07-28", "mcp-method": method}
    if "name" in params:
        headers["mcp-name"] = params["name"]
    return body, headers


async def call(client, auth, name, args, user=None, meta=None, extra_headers=None):
    body, headers = rpc("tools/call", {"name": name, "arguments": args}, meta)
    headers |= auth | (extra_headers or {}) | ({"x-user-token": user} if user else {})
    return await client.post("/mcp", json=body, headers=headers)
