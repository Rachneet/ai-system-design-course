"""Monthly budgets at org, team and app level, checked before each request against the ledger's running totals.

Lookups are cached for a couple of seconds per (org, team, app): budgets protect money over a month, so a
few seconds of staleness costs at most a few requests of overshoot, while a query per request would not scale.
"""

import time

from psycopg_pool import AsyncConnectionPool

CHECK = """
SELECT b.scope, coalesce(s.cost_usd, 0) AS spent, b.budget
FROM (VALUES ('org', %(org)s, (SELECT budget_usd_month FROM orgs WHERE id = %(org)s)),
             ('team', %(team)s, (SELECT budget_usd_month FROM teams WHERE id = %(team)s)),
             ('app', %(app)s, (SELECT budget_usd_month FROM apps WHERE id = %(app)s))) AS b(scope, scope_id, budget)
LEFT JOIN spend_monthly s ON s.scope = b.scope AND s.scope_id = b.scope_id AND s.month = date_trunc('month', now())::date
WHERE b.budget IS NOT NULL
"""


class Budgets:
    def __init__(self, pool: AsyncConnectionPool, ttl_s: float = 2.0, clock=time.monotonic):
        self.pool, self.ttl_s, self.clock = pool, ttl_s, clock
        self._cache: dict[tuple, tuple[float, str | None]] = {}

    async def exhausted(self, org: str, team: str, app: str) -> str | None:
        """The first scope whose monthly budget is used up, or None."""
        key = (org, team, app)
        hit = self._cache.get(key)
        if hit and self.clock() - hit[0] < self.ttl_s:
            return hit[1]
        async with self.pool.connection() as c:
            rows = await (await c.execute(CHECK, {"org": org, "team": team, "app": app})).fetchall()
        scope = next((r["scope"] for r in rows if r["spent"] >= r["budget"]), None)
        self._cache[key] = (self.clock(), scope)
        return scope

    def forget(self) -> None:
        self._cache.clear()
