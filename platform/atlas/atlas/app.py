"""Atlas: the registry of agents, MCP servers and agent skills your organisation has approved."""

import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .api import router
from .config import Settings, settings
from .db import open_pool

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)


def create_app(cfg: Settings = settings, upstream_transport=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = cfg
        app.state.upstream_transport = upstream_transport  # tests swap in a mock public registry
        app.state.pool = await open_pool(cfg.database_url, cfg.db_schema)
        yield
        await app.state.pool.close()

    app = FastAPI(title="Atlas", version="0.1.0", lifespan=lifespan)
    app.include_router(router)

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
