"""Shared token buckets in Postgres: one statement, row-locked by the upsert, so concurrent instances agree."""

from psycopg_pool import AsyncConnectionPool

TAKE = """
INSERT INTO buckets (key, tokens, last_allowed, updated_at)
VALUES (%(key)s, %(burst)s - %(cost)s, %(cost)s <= %(burst)s, now())
ON CONFLICT (key) DO UPDATE SET
  last_allowed = LEAST(%(burst)s, buckets.tokens + EXTRACT(EPOCH FROM now() - buckets.updated_at) * %(rate)s) >= %(cost)s,
  tokens = CASE
    WHEN LEAST(%(burst)s, buckets.tokens + EXTRACT(EPOCH FROM now() - buckets.updated_at) * %(rate)s) >= %(cost)s
    THEN LEAST(%(burst)s, buckets.tokens + EXTRACT(EPOCH FROM now() - buckets.updated_at) * %(rate)s) - %(cost)s
    ELSE LEAST(%(burst)s, buckets.tokens + EXTRACT(EPOCH FROM now() - buckets.updated_at) * %(rate)s)
  END,
  updated_at = now()
RETURNING last_allowed, tokens
"""


async def take(pool: AsyncConnectionPool, key: str, per_minute: int, cost: float = 1.0) -> float:
    """0 if allowed, else seconds until enough capacity refills. Burst equals one minute of capacity."""
    rate = per_minute / 60.0
    async with pool.connection() as c:
        row = await (
            await c.execute(TAKE, {"key": key, "burst": float(per_minute), "cost": float(cost), "rate": rate})
        ).fetchone()
    if row["last_allowed"]:
        return 0.0
    if cost > per_minute:
        return 60.0  # a single request larger than the whole per-minute budget never fits
    return max(0.001, (cost - row["tokens"]) / rate)


async def refund(pool: AsyncConnectionPool, key: str, per_minute: int, amount: float) -> None:
    """Give back over-estimated tokens once actual usage is known (never above the burst)."""
    if amount <= 0:
        return
    async with pool.connection() as c:
        await c.execute(
            "UPDATE buckets SET tokens = LEAST(%s, tokens + %s) WHERE key = %s", (float(per_minute), amount, key)
        )
