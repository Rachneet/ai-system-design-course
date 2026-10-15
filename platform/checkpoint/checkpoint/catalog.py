"""The tools an agent can reach: approved MCP servers from Atlas, their tools listed upstream and namespaced as
<server>__<tool>. Refreshed on a TTL; a server that disappears from Atlas (rejected, deprecated) disappears here.

When Atlas pins a server's tool list (toolsDigest, Atlas ADR 0004), the live tools/list must match it. A server whose
tools changed after review is quarantined: none of its tools are listed or callable until the list matches again or
a version with the new list is approved."""

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field

import httpx
import structlog

from . import metrics
from .upstream import Upstream, UpstreamError

SEP = "__"
TOOL_FIELDS = ("name", "title", "description", "inputSchema", "outputSchema", "annotations")
log = structlog.get_logger("checkpoint")


def tools_digest(tools: list[dict]) -> str:
    """Atlas's pin, computed the same way: tools sorted by name, reduced to TOOL_FIELDS, canonical JSON, sha256."""
    canon = sorted(({k: t[k] for k in TOOL_FIELDS if k in t} for t in tools), key=lambda t: t["name"])
    return "sha256:" + hashlib.sha256(json.dumps(canon, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def slug(name: str) -> str:
    last = name.rsplit("/", 1)[-1]
    return re.sub(r"[^a-z0-9]+", "-", last.lower()).strip("-") or "server"


@dataclass
class Server:
    name: str
    slug: str
    url: str
    digest: str
    upstream: Upstream
    pin: str = ""  # Atlas's toolsDigest; empty when the version has no pinned tool list
    tools: dict[str, dict] = field(default_factory=dict)
    drift: str | None = None  # the live digest, when it differs from the pin


class Catalog:
    def __init__(self, cfg, atlas_transport=None, upstream_transport=None):
        self.cfg = cfg
        self.atlas = httpx.AsyncClient(base_url=cfg.atlas_url, transport=atlas_transport, timeout=15)
        self.upstream_transport = upstream_transport
        self.servers: dict[str, Server] = {}
        self.loaded_at = 0.0
        self.lock = asyncio.Lock()

    async def _approved(self) -> list[dict]:
        out, cursor = [], None
        headers = {"authorization": f"Bearer {self.cfg.atlas_token}"} if self.cfg.atlas_token else {}
        while True:
            params = {"version": "latest", "limit": 100} | ({"cursor": cursor} if cursor else {})
            resp = await self.atlas.get("/v0/servers", params=params, headers=headers)
            resp.raise_for_status()
            page = resp.json()
            out += page.get("servers", [])
            cursor = (page.get("metadata") or {}).get("nextCursor")
            if not cursor:
                return out

    async def refresh(self, force: bool = False) -> None:
        async with self.lock:
            if force or time.monotonic() - self.loaded_at >= self.cfg.catalog_ttl_s:
                await self._reload()
                stale = list(self.servers.values())  # every TTL, list every server's tools again: they can change
            else:
                # Servers whose tool list failed to load are retried on every call; quarantined ones wait for the TTL.
                stale = [s for s in self.servers.values() if not s.tools and not s.drift]
        await asyncio.gather(*(self._load_tools(s) for s in stale))

    async def _reload(self) -> None:
        entries = await self._approved()
        fresh: dict[str, Server] = {}
        for entry in entries:
            doc = entry.get("server") or {}
            remote = next((r for r in doc.get("remotes") or [] if r.get("type") == "streamable-http"), None)
            if not remote or not str(remote.get("url", "")).startswith("https://"):
                continue  # Checkpoint reaches remote servers over HTTPS only
            review = (entry.get("_meta") or {}).get("io.atlas/review") or {}
            pin = review.get("toolsDigest") or ""
            if self.cfg.require_pinned_tools and not pin:
                continue  # policy: only servers whose tool list was reviewed
            s = slug(doc["name"])
            while s in fresh:
                s += "-x"
            old = self.servers.get(s)
            if old and old.name == doc["name"] and old.url == remote["url"]:
                old.digest, old.pin = review.get("digest", ""), pin
                fresh[s] = old
                continue
            up = Upstream(
                doc["name"], remote["url"], self.cfg.upstream_credentials.get(doc["name"]), self.upstream_transport
            )
            fresh[s] = Server(doc["name"], s, remote["url"], review.get("digest", ""), up, pin)
        for s, server in self.servers.items():
            if fresh.get(s) is not server:
                await server.upstream.close()
        self.servers, self.loaded_at = fresh, time.monotonic()

    async def _load_tools(self, server: Server) -> None:
        try:
            result = await server.upstream.call("tools/list", {})
        except (UpstreamError, httpx.HTTPError) as e:
            log.warning("tools_list_failed", server=server.name, error=f"{type(e).__name__}: {e}")
            server.tools = {}
            return
        tools = [t for t in result.get("tools", []) if isinstance(t, dict) and isinstance(t.get("name"), str)]
        live = tools_digest(tools)
        if server.pin and live != server.pin:
            log.warning("tools_changed", server=server.name, pinned=server.pin, live=live)
            metrics.tools_changed.labels(server=server.name).inc()
            server.tools, server.drift = {}, live
            return
        server.tools, server.drift = {t["name"]: t for t in tools}, None

    def find(self, namespaced: str) -> tuple[Server, dict] | None:
        server_slug, sep, tool = namespaced.partition(SEP)
        server = self.servers.get(server_slug)
        if not sep or not server or tool not in server.tools:
            return None
        return server, server.tools[tool]

    def quarantined(self, namespaced: str) -> Server | None:
        server = self.servers.get(namespaced.partition(SEP)[0])
        return server if server and server.drift else None

    def all_tools(self):
        for server in self.servers.values():
            for name, tool in server.tools.items():
                yield f"{server.slug}{SEP}{name}", server, tool

    async def close(self) -> None:
        await self.atlas.aclose()
        for s in self.servers.values():
            await s.upstream.close()
