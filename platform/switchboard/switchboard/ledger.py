"""Usage ledger: an append-only row per request plus monthly totals per scope.

Writes are batched: requests enqueue events in memory and a background task flushes them every interval in one
transaction, aggregating spend per scope. Per-request writes made the three monthly totals hot rows under load.
Spend is added only for rows the insert actually created, so retrying a failed batch never double counts, and
scopes are updated in sorted order so concurrent instances cannot deadlock.

Trade-off: a hard crash loses at most one interval of usage records (graceful shutdown flushes). See ADR 0002.
"""

import asyncio
import contextlib
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

import structlog
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from . import metrics
from .keys import Caller

log = structlog.get_logger("switchboard.ledger")

INSERT = """
INSERT INTO usage_events (request_id, key_id, app_id, team_id, org_id, requested_model, served_model, fallback, status,
  stream, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd, latency_ms, ttfb_ms,
  pii_findings, error_type)
VALUES (%(request_id)s, %(key_id)s, %(app_id)s, %(team_id)s, %(org_id)s, %(requested_model)s, %(served_model)s,
  %(fallback)s, %(status)s, %(stream)s, %(input_tokens)s, %(output_tokens)s, %(cache_read)s, %(cache_write)s,
  %(cost_usd)s, %(latency_ms)s, %(ttfb_ms)s, %(pii_findings)s, %(error_type)s)
ON CONFLICT (request_id) DO NOTHING
RETURNING request_id
"""

SPEND = """
INSERT INTO spend_monthly (scope, scope_id, month, cost_usd, requests)
VALUES (%s, %s, date_trunc('month', now())::date, %s, %s)
ON CONFLICT (scope, scope_id, month) DO UPDATE
SET cost_usd = spend_monthly.cost_usd + EXCLUDED.cost_usd, requests = spend_monthly.requests + EXCLUDED.requests
"""


def to_row(caller: Caller, event: dict, cost: Decimal) -> dict:
    usage = event.get("usage", {})
    return {
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


class LedgerWriter:
    def __init__(self, pool: AsyncConnectionPool, interval_s: float = 0.5, max_queue: int = 100_000):
        self.pool, self.interval_s, self.max_queue = pool, interval_s, max_queue
        self.queue: list[tuple[dict, tuple | None, int]] = []  # (row, audit, retention_days)
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    def add(self, caller: Caller, event: dict, cost: Decimal, audit: tuple[dict, str | None] | None) -> None:
        if len(self.queue) >= self.max_queue:  # the database has been down a long time: shed, loudly
            self.queue.pop(0)
            metrics.ledger_dropped.inc()
        self.queue.append((to_row(caller, event, cost), audit, caller.retention_days))

    async def flush(self) -> int:
        async with self._lock:
            batch, self.queue = self.queue, []
            if not batch:
                return 0
            try:
                written = await self._write(batch)
            except Exception:
                log.exception("ledger_flush_failed", queued=len(batch))
                self.queue[:0] = batch  # retry next interval; spend is only counted for rows actually inserted
                metrics.ledger_flush_failures.inc()
                return 0
            metrics.ledger_batch.observe(len(batch))
            return written

    async def _write(self, batch: list) -> int:
        rows = [row for row, _, _ in batch]
        async with self.pool.connection() as c, c.transaction():
            async with c.cursor() as cur:
                await cur.executemany(INSERT, rows, returning=True)
                inserted = set()
                while True:
                    hit = await cur.fetchone()
                    if hit:
                        inserted.add(hit["request_id"])
                    if not cur.nextset():
                        break
            spend: dict[tuple[str, str], list] = defaultdict(lambda: [Decimal(0), 0])
            keys = set()
            for row in rows:
                if row["request_id"] not in inserted:
                    continue
                keys.add(row["key_id"])
                for scope in ("org", "team", "app"):
                    total = spend[(scope, row[f"{scope}_id"])]
                    total[0] += row["cost_usd"]
                    total[1] += 1
            for (scope, scope_id), (cost, count) in sorted(spend.items()):  # fixed order: no deadlocks
                await c.execute(SPEND, (scope, scope_id, cost, count))
            if keys:
                await c.execute("UPDATE api_keys SET last_used_at = now() WHERE id = ANY(%s)", (sorted(keys),))
            audits = [
                (row["request_id"], row["app_id"], Jsonb(audit[0]), audit[1], timedelta(days=days))
                for row, audit, days in batch
                if audit is not None and row["request_id"] in inserted
            ]
            if audits:
                async with c.cursor() as cur:
                    await cur.executemany(
                        "INSERT INTO audit_bodies (request_id, app_id, request, response, expires_at) "
                        "VALUES (%s, %s, %s, %s, now() + %s)",
                        audits,
                    )
        return len(inserted)

    async def start(self) -> None:
        async def loop():
            while True:
                await asyncio.sleep(self.interval_s)
                await self.flush()

        self._task = asyncio.create_task(loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self.flush()
