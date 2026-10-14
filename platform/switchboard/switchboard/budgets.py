"""Monthly budgets at org, team and app level. Checked before a request; spend is recorded after it."""

from psycopg_pool import AsyncConnectionPool

CHECK = """
SELECT s.scope, coalesce(s.cost_usd, 0) AS spent, b.budget
FROM (VALUES ('org', %(org)s, (SELECT budget_usd_month FROM orgs WHERE id = %(org)s)),
             ('team', %(team)s, (SELECT budget_usd_month FROM teams WHERE id = %(team)s)),
             ('app', %(app)s, (SELECT budget_usd_month FROM apps WHERE id = %(app)s))) AS b(scope, scope_id, budget)
LEFT JOIN spend_monthly s ON s.scope = b.scope AND s.scope_id = b.scope_id AND s.month = date_trunc('month', now())::date
WHERE b.budget IS NOT NULL
"""


async def exhausted(pool: AsyncConnectionPool, org: str, team: str, app: str) -> str | None:
    """The first scope whose monthly budget is used up, or None. Requests in flight may overshoot slightly."""
    async with pool.connection() as c:
        rows = await (await c.execute(CHECK, {"org": org, "team": team, "app": app})).fetchall()
    for r in rows:
        if r["spent"] >= r["budget"]:
            return r["scope"]
    return None
