"""Usage ledger: one append-only row per request plus monthly totals, written in a single transaction."""

from datetime import timedelta
from decimal import Decimal

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from .keys import Caller

INSERT = """
INSERT INTO usage_events (request_id, key_id, app_id, team_id, org_id, requested_model, served_model, fallback, status,
  stream, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd, latency_ms, ttfb_ms,
  pii_findings, error_type)
VALUES (%(request_id)s, %(key_id)s, %(app_id)s, %(team_id)s, %(org_id)s, %(requested_model)s, %(served_model)s,
  %(fallback)s, %(status)s, %(stream)s, %(input_tokens)s, %(output_tokens)s, %(cache_read)s, %(cache_write)s,
  %(cost_usd)s, %(latency_ms)s, %(ttfb_ms)s, %(pii_findings)s, %(error_type)s)
ON CONFLICT (request_id) DO NOTHING
RETURNING id
"""

SPEND = """
INSERT INTO spend_monthly (scope, scope_id, month, cost_usd, requests)
VALUES (%s, %s, date_trunc('month', now())::date, %s, 1)
ON CONFLICT (scope, scope_id, month) DO UPDATE
SET cost_usd = spend_monthly.cost_usd + EXCLUDED.cost_usd, requests = spend_monthly.requests + 1
"""


async def record(
    pool: AsyncConnectionPool, caller: Caller, event: dict, cost: Decimal, audit: tuple[dict, str | None] | None = None
) -> None:
    usage = event.get("usage", {})
    row = {
        **{
            k: event.get(k)
            for k in (
                "request_id",
                "requested_model",
                "served_model",
                "status",
                "stream",
                "latency_ms",
                "ttfb_ms",
                "error_type",
            )
        },
        "key_id": caller.key_id,
        "app_id": caller.app_id,
        "team_id": caller.team_id,
        "org_id": caller.org_id,
        "fallback": bool(event.get("served_model")) and event.get("served_model") != event.get("requested_model"),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cache_read": usage.get("cache_read_input_tokens", 0),
        "cache_write": usage.get("cache_creation_input_tokens", 0),
        "cost_usd": cost,
        "pii_findings": event.get("pii_findings", 0),
    }
    async with pool.connection() as c, c.transaction():
        inserted = await (await c.execute(INSERT, row)).fetchone()
        if inserted is None:
            return  # already recorded (idempotent on request_id)
        for scope, scope_id in (("org", caller.org_id), ("team", caller.team_id), ("app", caller.app_id)):
            await c.execute(SPEND, (scope, scope_id, cost))
        await c.execute("UPDATE api_keys SET last_used_at = now() WHERE id = %s", (caller.key_id,))
        if audit is not None:
            request_body, response_text = audit
            await c.execute(
                "INSERT INTO audit_bodies (request_id, app_id, request, response, expires_at) "
                "VALUES (%s, %s, %s, %s, now() + %s)",
                (
                    row["request_id"],
                    caller.app_id,
                    Jsonb(request_body),
                    response_text,
                    timedelta(days=caller.retention_days),
                ),
            )
