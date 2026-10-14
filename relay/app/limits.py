"""Per-customer rate limits and daily token budgets, in Postgres so every API instance shares them."""

import math
from datetime import UTC, datetime

from fastapi import HTTPException

from .db import Store


async def take(store: Store, key: str, rate_per_s: float, burst: int, cost: float = 1.0) -> float:
    """Token bucket. Returns 0 if allowed, otherwise the seconds to wait. Row lock makes it safe under concurrency."""
    async with store.conn() as c, c.transaction():
        row = await (
            await c.execute("SELECT tokens, updated_at FROM rate_limits WHERE key = %s FOR UPDATE", (key,))
        ).fetchone()
        now = datetime.now(UTC)
        if row is None:
            level = float(burst)
        else:
            level = min(burst, row["tokens"] + (now - row["updated_at"]).total_seconds() * rate_per_s)
        allowed = level >= cost
        new_level = level - cost if allowed else level
        await c.execute(
            "INSERT INTO rate_limits (key, tokens, updated_at) VALUES (%s, %s, %s) "
            "ON CONFLICT (key) DO UPDATE SET tokens = EXCLUDED.tokens, updated_at = EXCLUDED.updated_at",
            (key, new_level, now),
        )
    return 0.0 if allowed else (cost - level) / rate_per_s


async def enforce_rate(store: Store, customer_id: str, per_minute: float, burst: int) -> None:
    wait = await take(store, f"chat:{customer_id}", per_minute / 60, burst)
    if wait:
        raise HTTPException(
            429, "Too many messages. Please wait a moment.", headers={"Retry-After": str(math.ceil(wait))}
        )


async def enforce_budget(store: Store, customer_id: str, daily_tokens: int) -> None:
    async with store.conn() as c:
        row = await (
            await c.execute(
                "SELECT tokens FROM usage_daily WHERE customer_id = %s AND day = current_date", (customer_id,)
            )
        ).fetchone()
    if row and row["tokens"] >= daily_tokens:
        raise HTTPException(
            429,
            "You've reached today's usage limit. Please try again tomorrow or contact support.",
            headers={"Retry-After": "3600"},
        )


async def record_usage(store: Store, customer_id: str, tokens: int, cost_usd: float) -> None:
    async with store.conn() as c:
        await c.execute(
            "INSERT INTO usage_daily (customer_id, day, tokens, cost_usd) VALUES (%s, current_date, %s, %s) "
            "ON CONFLICT (customer_id, day) DO UPDATE SET tokens = usage_daily.tokens + EXCLUDED.tokens, "
            "cost_usd = usage_daily.cost_usd + EXCLUDED.cost_usd",
            (customer_id, tokens, cost_usd),
        )
