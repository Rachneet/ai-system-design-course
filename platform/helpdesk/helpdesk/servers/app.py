"""One process serving the four systems at /<system>/mcp. In production each is its own service on a network only
Checkpoint can reach."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response
from pydantic_settings import BaseSettings, SettingsConfigDict

from .mcp import AssertionVerifier
from .systems import Store, all_servers


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HELPDESK_SYSTEMS_", extra="ignore")

    checkpoint_jwks_url: str = "http://localhost:8002/.well-known/jwks.json"


def create_servers_app(cfg: ServerSettings | None = None, store: Store | None = None, transport=None) -> FastAPI:
    cfg = cfg or ServerSettings()
    servers = all_servers(store or Store())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.verifier = AssertionVerifier(cfg.checkpoint_jwks_url, transport)
        yield
        await app.state.verifier.close()

    app = FastAPI(title="Helpdesk systems", lifespan=lifespan)

    @app.post("/{system}/mcp")
    async def mcp(system: str, request: Request) -> Response:
        server = servers.get(system)
        if server is None:
            return Response(status_code=404)
        return await server.handle(request, request.app.state.verifier)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    app.state.servers = servers
    return app
