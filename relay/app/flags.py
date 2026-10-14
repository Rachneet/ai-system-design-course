"""Kill switches and runtime flags, stored in Postgres and cached briefly so a flip takes effect within seconds.

tools.disabled        list of tool names to withdraw, e.g. ["issue_refund"]
agent.enabled         false pauses the assistant and shows a support contact instead
agent.force_fallback  true sends all traffic to the fallback model
routing.enabled       true sends simple intents to the small model
"""

import time

from psycopg.types.json import Jsonb

from .db import Store

DEFAULTS = {
    "tools.disabled": [],
    "agent.enabled": True,
    "agent.force_fallback": False,
    "routing.enabled": False,
}
TTL_S = 10.0


class Flags:
    def __init__(self, store: Store, ttl_s: float = TTL_S, clock=time.monotonic):
        self.store, self.ttl_s, self.clock = store, ttl_s, clock
        self._cache: dict = {}
        self._loaded_at = -1e9

    async def all(self) -> dict:
        if self.clock() - self._loaded_at > self.ttl_s:
            async with self.store.conn() as c:
                rows = await (await c.execute("SELECT key, value FROM flags")).fetchall()
            self._cache = DEFAULTS | {r["key"]: r["value"] for r in rows}
            self._loaded_at = self.clock()
        return self._cache

    async def get(self, key: str):
        return (await self.all())[key]

    async def set(self, key: str, value, by: str) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        async with self.store.conn() as c:
            await c.execute(
                "INSERT INTO flags (key, value, updated_by) VALUES (%s, %s, %s) ON CONFLICT (key) DO UPDATE "
                "SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = now()",
                (key, Jsonb(value), by),
            )
        self._loaded_at = -1e9  # this instance sees it immediately; others within ttl_s
