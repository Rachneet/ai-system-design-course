"""Checkpoint: the MCP gateway every agent tool call passes through."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .api import router
from .catalog import Catalog
from .config import Settings, settings
from .db import open_pool
from .gateway import handle
from .identity import Signer, UserVerifier
from .limits import Buckets
from .policy import Policy

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)


def create_app(
    cfg: Settings = settings, atlas_transport=None, upstream_transport=None, policy_text: str | None = None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = cfg
        app.state.policy = Policy(policy_text if policy_text is not None else Path(cfg.policy_file).read_text())
        app.state.pool = await open_pool(cfg.database_url, cfg.db_schema)
        app.state.catalog = Catalog(cfg, atlas_transport, upstream_transport)
        app.state.users = UserVerifier(cfg)
        app.state.signer = Signer(cfg.assertion_private_key, cfg.assertion_ttl_s)
        app.state.limits = Buckets(cfg.calls_per_minute)
        yield
        await app.state.catalog.close()
        await app.state.pool.close()

    app = FastAPI(title="Checkpoint", version="0.1.0", lifespan=lifespan)
    app.include_router(router)

    @app.post("/mcp", tags=["mcp"])
    async def mcp_endpoint(request: Request) -> Response:
        return await handle(request)

    @app.api_route("/mcp", methods=["GET", "DELETE"], include_in_schema=False)
    async def no_streams() -> Response:
        return Response(status_code=405, headers={"allow": "POST"})  # 2026-07-28 has no GET stream or sessions

    @app.get("/healthz", tags=["ops"])
    async def healthz():
        return {"ok": True}

    @app.get("/readyz", tags=["ops"])
    async def readyz(request: Request):
        async with request.app.state.pool.connection() as c:
            await c.execute("SELECT 1")
        return {"ok": True}

    @app.get("/metrics", tags=["ops"])
    async def metrics_endpoint():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
