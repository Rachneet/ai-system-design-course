"""The whole platform in one process: real Switchboard, Atlas and Checkpoint (each on its own schema of one embedded
Postgres), Helpdesk's systems of record as MCP servers, and Helpdesk itself, connected by in-process transports and
provisioned through the same admin APIs as production. Only the model provider is scripted."""

import os
from contextlib import AsyncExitStack
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from alembic import command
from alembic.config import Config
from atlas.app import create_app as atlas_app
from atlas.config import Settings as AtlasSettings
from checkpoint.app import create_app as checkpoint_app
from checkpoint.config import Settings as CheckpointSettings
from switchboard.app import create_app as switchboard_app
from switchboard.config import Settings as SwitchboardSettings

from helpdesk.app import create_app as helpdesk_app
from helpdesk.config import AgentSecrets
from helpdesk.config import Settings as HelpdeskSettings
from helpdesk.identity import mint
from helpdesk.provision import provision
from helpdesk.roster import load
from helpdesk.servers.app import ServerSettings, create_servers_app
from helpdesk.servers.systems import Store
from tests import provider

HERE = Path(__file__).resolve().parents[1]
PLATFORM = HERE.parent
USER_SECRET = "helpdesk-user-jwt-secret-for-tests-0123456789"
ADMIN = "admin-test-token-0123456789"
APP_ROLE = "helpdesk_app"
PRICES = [2.0, 0.0, 0.2, 8.0]  # USD per million tokens: input, cache write, cache read, output
URLS = {
    "switchboard": "http://switchboard.internal",
    "atlas": "https://atlas.internal",
    "checkpoint": "https://checkpoint.internal",
    "systems": "https://systems.internal",
    "helpdesk": "https://helpdesk.internal",
}


def migrate(service: str, uri: str, schema: str, prefix: str) -> None:
    os.environ[f"{prefix}_DATABASE_URL"] = uri
    os.environ[f"{prefix}_DB_SCHEMA"] = schema
    root = HERE if service == "helpdesk" else PLATFORM / service
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(cfg, "head")


def schema(uri: str) -> str:
    name = f"t_{uuid4().hex[:10]}"
    with psycopg.connect(uri, autocommit=True) as c:
        c.execute(f"CREATE SCHEMA {name}")
    return name


def as_app_role(uri: str) -> str:
    """The same database as a role without superuser or BYPASSRLS, so row-level security applies."""
    return uri.replace("postgres:@", f"{APP_ROLE}:@", 1)


class Platform:
    def __init__(self, pg_uri: str, **helpdesk_over):
        self.pg_uri, self.over = pg_uri, helpdesk_over
        self.store = Store()
        self.schemas = {s: schema(pg_uri) for s in ("switchboard", "atlas", "checkpoint", "helpdesk")}
        for service, prefix in (("switchboard", "SWITCHBOARD"), ("atlas", "ATLAS"), ("checkpoint", "CHECKPOINT")):
            migrate(service, pg_uri, self.schemas[service], prefix)
        os.environ["HELPDESK_APP_ROLE"] = APP_ROLE
        migrate("helpdesk", pg_uri, self.schemas["helpdesk"], "HELPDESK")

    async def __aenter__(self):
        provider.reset()
        roster = load(str(HERE / "config/agents.toml"), str(HERE / "config/models.toml"), str(HERE / "skills"))
        models = {m: {"provider": "mock", "prices": PRICES} for m in roster.models.values()}
        self.sb = switchboard_app(
            SwitchboardSettings(
                database_url=self.pg_uri,
                db_schema=self.schemas["switchboard"],
                admin_token=ADMIN,
                providers={"mock": {"base_url": "http://provider/v1", "api_key": "provider-secret"}},
                chat_models=models,
                budget_cache_s=0.0,
            ),
            transport=httpx.ASGITransport(app=provider.app),
        )
        self.atlas = atlas_app(
            AtlasSettings(database_url=self.pg_uri, db_schema=self.schemas["atlas"], admin_token=ADMIN)
        )
        self.cp_cfg = CheckpointSettings(
            database_url=self.pg_uri,
            db_schema=self.schemas["checkpoint"],
            admin_token=ADMIN,
            atlas_url=URLS["atlas"],
            user_jwt_secret=USER_SECRET,
            require_pinned_tools=True,
            calls_per_minute=600,
        )

        async def systems(scope, receive, send):  # Checkpoint calls the systems, which fetch Checkpoint's JWKS
            await self.systems(scope, receive, send)

        self.cp = checkpoint_app(
            self.cp_cfg,
            atlas_transport=httpx.ASGITransport(app=self.atlas),
            upstream_transport=httpx.ASGITransport(app=systems),
            policy_text=(HERE / "policies" / "helpdesk.cedar").read_text(),
        )
        self.systems = create_servers_app(
            ServerSettings(checkpoint_jwks_url=f"{URLS['checkpoint']}/.well-known/jwks.json"),
            self.store,
            transport=httpx.ASGITransport(app=self.cp),
        )
        self.hd_cfg = HelpdeskSettings(
            database_url=as_app_role(self.pg_uri),
            db_schema=self.schemas["helpdesk"],
            admin_token=ADMIN,
            switchboard_url=URLS["switchboard"],
            checkpoint_url=URLS["checkpoint"],
            atlas_url=URLS["atlas"],
            switchboard_admin_token=ADMIN,
            checkpoint_admin_token=ADMIN,
            user_jwt_secret=USER_SECRET,
            dev_tokens=True,
            agents_file=str(HERE / "config/agents.toml"),
            models_file=str(HERE / "config/models.toml"),
            skills_dir=str(HERE / "skills"),
            **self.over,
        )
        self.hd = helpdesk_app(
            self.hd_cfg,
            switchboard_transport=httpx.ASGITransport(app=self.sb),
            checkpoint_transport=httpx.ASGITransport(app=self.cp),
            atlas_transport=httpx.ASGITransport(app=self.atlas),
        )
        self.stack = AsyncExitStack()
        for app in (self.sb, self.atlas, self.cp, self.systems, self.hd):
            await self.stack.enter_async_context(app.router.lifespan_context(app))

        def client(app, base, token=None):
            headers = {"authorization": f"Bearer {token}"} if token else {}
            return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=base, headers=headers)

        self.admin = {
            "switchboard": client(self.sb, URLS["switchboard"], ADMIN),
            "atlas": client(self.atlas, URLS["atlas"], ADMIN),
            "checkpoint": client(self.cp, URLS["checkpoint"], ADMIN),
            "helpdesk": client(self.hd, URLS["helpdesk"], ADMIN),
        }
        for c in self.admin.values():
            await self.stack.enter_async_context(c)
        self.secrets = await provision(
            self.admin["switchboard"],
            self.admin["atlas"],
            self.admin["checkpoint"],
            roster,
            env="evals",
            skills_dir=str(HERE / "skills"),
            systems_url=URLS["systems"],
            base_url=URLS["helpdesk"],
        )
        self.cp_cfg.atlas_token = self.secrets["atlas_reader_token"]
        self.hd_cfg.agents = {k: AgentSecrets(**v) for k, v in self.secrets["agents"].items()}
        self.hd_cfg.console_tokens = self.secrets["console_tokens"]
        self.hd_cfg.atlas_token = self.secrets["atlas_reader_token"]
        self.http = await self.stack.enter_async_context(client(self.hd, URLS["helpdesk"]))
        return self

    async def __aexit__(self, *exc):
        await self.stack.aclose()

    # ---------- helpers for tests ----------

    @staticmethod
    def user(sub: str, tenant: str, *roles: str) -> dict:
        return {"authorization": f"Bearer {mint(USER_SECRET, sub, tenant, roles or ('staff',))}"}

    def script(self, **turns) -> None:
        provider.state["script"].update({k.replace("_", "-"): list(v) for k, v in turns.items()})

    async def open(self, who: dict, text: str) -> dict:
        r = await self.http.post("/v1/tickets", json={"message": text}, headers=who)
        assert r.status_code == 201, r.text
        return r.json()

    async def trace(self, ticket_id: str, supervisor: dict) -> dict:
        r = await self.http.get(f"/console/tickets/{ticket_id}/trace", headers=supervisor)
        assert r.status_code == 200, r.text
        return r.json()

    async def decisions(self, **params) -> list[dict]:
        r = await self.admin["checkpoint"].get("/admin/decisions", params={"limit": 1000} | params)
        return r.json()["decisions"]

    async def settle(self) -> None:
        await self.sb.state.gateway.drain()
