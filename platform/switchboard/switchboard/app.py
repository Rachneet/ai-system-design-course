"""Switchboard: an AI gateway. Data plane at /v1/messages and /v1/chat/completions, control plane at /admin."""

import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .admin import router as admin_router
from .config import Settings, settings
from .db import open_pool
from .gateway import Gateway
from .upstream import ChatUpstream, Upstream

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)


def create_app(cfg: Settings = settings, transport=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not cfg.anthropic_api_key and not cfg.providers and transport is None:
            raise RuntimeError("Set SWITCHBOARD_ANTHROPIC_API_KEY or SWITCHBOARD_PROVIDERS")
        app.state.settings = cfg
        app.state.pool = await open_pool(cfg.database_url, cfg.db_schema)
        upstream = Upstream(
            cfg.anthropic_base_url,
            cfg.anthropic_api_key,
            cfg.connect_timeout_s,
            cfg.read_timeout_s,
            transport=transport,
        )
        chat_upstreams = {
            name: ChatUpstream(
                p["base_url"], p.get("api_key", ""), cfg.connect_timeout_s, cfg.read_timeout_s, transport
            )
            for name, p in cfg.providers.items()
        }
        app.state.gateway = Gateway(cfg, app.state.pool, upstream, chat_upstreams)
        await app.state.gateway.start()
        yield
        await app.state.gateway.stop()  # finish requests' bookkeeping and flush the ledger before exiting
        await upstream.close()
        for c in chat_upstreams.values():
            await c.close()
        await app.state.pool.close()

    app = FastAPI(title="Switchboard", version="0.1.0", lifespan=lifespan)
    app.include_router(admin_router)

    @app.post("/v1/messages", tags=["data plane"])
    async def messages(request: Request) -> Response:
        """Anthropic Messages API, proxied with keys, limits, budgets, PII policy, fallbacks and metering."""
        return await request.app.state.gateway.handle(request)

    @app.post("/v1/chat/completions", tags=["data plane"])
    async def chat_completions(request: Request) -> Response:
        """OpenAI-compatible Chat Completions for every other provider, with the same controls and metering."""
        return await request.app.state.gateway.handle(request, chat=True)

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
