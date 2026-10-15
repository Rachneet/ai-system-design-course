"""Helpdesk OS: a multi-tenant support platform whose agents run on Switchboard, Atlas and Checkpoint."""

import logging
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .api import router
from .config import Settings, settings
from .db import open_pool
from .identity import Users
from .llm import Switchboard
from .roster import load
from .runtime import Runtime
from .tools import Checkpoint
from .web import page

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)


def create_app(
    cfg: Settings = settings, switchboard_transport=None, checkpoint_transport=None, atlas_transport=None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = cfg
        app.state.roster = load(cfg.agents_file, cfg.models_file, cfg.skills_dir)
        app.state.pool = await open_pool(cfg.database_url, cfg.db_schema)
        app.state.users = Users(cfg, app.state.roster.tenants)
        app.state.switchboard = Switchboard(cfg.switchboard_url, switchboard_transport)
        app.state.checkpoint = Checkpoint(cfg.checkpoint_url, checkpoint_transport)
        app.state.atlas = httpx.AsyncClient(base_url=cfg.atlas_url, transport=atlas_transport, timeout=15)
        app.state.runtime = Runtime(cfg, app.state.roster, app.state.pool, app.state.switchboard, app.state.checkpoint)
        yield
        await app.state.atlas.aclose()
        await app.state.checkpoint.close()
        await app.state.switchboard.close()
        await app.state.pool.close()

    app = FastAPI(title="Helpdesk OS", version="0.1.0", lifespan=lifespan)
    app.include_router(router)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def customer_desk():
        return page("customer")

    @app.get("/staff", response_class=HTMLResponse, include_in_schema=False)
    async def employee_desk():
        return page("employee")

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
