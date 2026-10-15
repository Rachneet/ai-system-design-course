"""The tools an agent can reach: approved MCP servers from Atlas, their tools listed upstream and namespaced as
<server>__<tool>. Refreshed on a TTL; a server that disappears from Atlas (rejected, deprecated) disappears here."""

import asyncio
import re
import time
from dataclasses import dataclass, field

import httpx

from .upstream import Upstream, UpstreamError

SEP = "__"


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
    tools: dict[str, dict] = field(default_factory=dict)


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
            if not force and time.monotonic() - self.loaded_at < self.cfg.catalog_ttl_s:
                return
            entries = await self._approved()
            fresh: dict[str, Server] = {}
            for entry in entries:
                doc = entry.get("server") or {}
                remote = next((r for r in doc.get("remotes") or [] if r.get("type") == "streamable-http"), None)
                if not remote or not str(remote.get("url", "")).startswith("https://"):
                    continue  # Checkpoint reaches remote servers over HTTPS only
                s = slug(doc["name"])
                while s in fresh:
                    s += "-x"
                old = self.servers.get(s)
                review = (entry.get("_meta") or {}).get("io.atlas/review") or {}
                if old and old.name == doc["name"] and old.url == remote["url"]:
                    old.digest = review.get("digest", "")
                    fresh[s] = old
                    continue
                up = Upstream(
                    doc["name"], remote["url"], self.cfg.upstream_credentials.get(doc["name"]), self.upstream_transport
                )
                fresh[s] = Server(doc["name"], s, remote["url"], review.get("digest", ""), up)
            for s, server in self.servers.items():
                if fresh.get(s) is not server:
                    await server.upstream.close()
            self.servers, self.loaded_at = fresh, time.monotonic()
        await asyncio.gather(*(self._load_tools(s) for s in self.servers.values() if not s.tools))

    async def _load_tools(self, server: Server) -> None:
        try:
            result = await server.upstream.call("tools/list", {})
        except (UpstreamError, httpx.HTTPError):
            server.tools = {}
            return
        server.tools = {t["name"]: t for t in result.get("tools", []) if isinstance(t, dict) and t.get("name")}

    def find(self, namespaced: str) -> tuple[Server, dict] | None:
        server_slug, sep, tool = namespaced.partition(SEP)
        server = self.servers.get(server_slug)
        if not sep or not server or tool not in server.tools:
            return None
        return server, server.tools[tool]

    def all_tools(self):
        for server in self.servers.values():
            for name, tool in server.tools.items():
                yield f"{server.slug}{SEP}{name}", server, tool

    async def close(self) -> None:
        await self.atlas.aclose()
        for s in self.servers.values():
            await s.upstream.close()
