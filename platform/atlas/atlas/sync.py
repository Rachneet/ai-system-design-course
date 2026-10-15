"""Curated sync from the public MCP registry. Imported servers land in review with source='upstream' and no owning
team: the public registry says a server exists, not that your organisation trusts it."""

import httpx

from . import store
from .auth import Principal
from .kinds import Invalid, parse_mcp_server

SYNC = Principal("sync:upstream", None, frozenset({"publisher"}))


async def import_mcp(pool, cfg, limit: int, search: str | None = None, transport=None) -> dict:
    imported, skipped, invalid, cursor = 0, 0, 0, None
    async with httpx.AsyncClient(base_url=cfg.upstream_registry_url, transport=transport, timeout=20) as client:
        while imported + skipped + invalid < limit:
            params = {"limit": min(100, limit), "version": "latest"} | ({"cursor": cursor} if cursor else {})
            if search:
                params["search"] = search
            resp = await client.get("/v0/servers", params=params)
            resp.raise_for_status()
            page = resp.json()
            for entry in page.get("servers", []):
                if imported + skipped + invalid >= limit:
                    break
                try:
                    p = parse_mcp_server(entry.get("server") or {})
                    await store.publish(pool, p, SYNC, None, None, cfg, source="upstream")
                    imported += 1
                except store.Conflict:
                    skipped += 1  # already imported this version
                except Invalid:
                    invalid += 1
            cursor = (page.get("metadata") or {}).get("nextCursor")
            if not cursor or not page.get("servers"):
                break
    return {"imported": imported, "already_present": skipped, "invalid": invalid}
