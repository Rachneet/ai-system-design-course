"""A general Postgres job queue. Enqueue in the same transaction as the data that triggers the job (outbox)."""

import random
from datetime import timedelta

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from . import metrics
from .db import Store
from .telemetry import inject, link_from, tracer

MAX_ATTEMPTS = 5

CLAIM = """
UPDATE jobs SET status = 'running', attempts = attempts + 1
WHERE id = (
  SELECT id FROM jobs WHERE status = 'queued' AND run_after <= now()
  ORDER BY run_after FOR UPDATE SKIP LOCKED LIMIT 1
)
RETURNING id, kind, payload, attempts
"""


async def enqueue(
    conn: AsyncConnection, kind: str, dedupe_key: str, payload: dict, delay_s: float = 0
) -> None:
    """At most one queued job per (kind, dedupe_key): a newer request pushes the run time back (debounce)."""
    await conn.execute(
        "INSERT INTO jobs (kind, dedupe_key, payload, run_after) VALUES (%s, %s, %s, now() + %s) "
        "ON CONFLICT (kind, dedupe_key) WHERE status = 'queued' "
        "DO UPDATE SET payload = EXCLUDED.payload, run_after = EXCLUDED.run_after",
        (kind, dedupe_key, Jsonb(payload | {"trace": inject()}), timedelta(seconds=delay_s)),
    )


async def run_ready(store: Store, handlers: dict, max_jobs: int = 100) -> int:
    done = 0
    while done < max_jobs:
        async with store.conn() as c:
            job = await (await c.execute(CLAIM)).fetchone()
        if job is None:
            return done
        payload = dict(job["payload"])
        with tracer.start_as_current_span(
            f"job {job['kind']}", links=link_from(payload.pop("trace", None))
        ) as span:
            span.set_attributes({"relay.job.id": job["id"], "relay.job.attempt": job["attempts"]})
            try:
                await handlers[job["kind"]](payload)
                status, error, delay = "done", None, 0.0
            except Exception as e:  # noqa: BLE001 - one bad job must not stop the worker
                status = "queued" if job["attempts"] < MAX_ATTEMPTS else "dead"
                error, delay = repr(e)[:500], min(600, 2 ** job["attempts"]) + random.random()
                span.record_exception(e)
        metrics.jobs.labels(kind=job["kind"], outcome=status).inc()
        async with store.conn() as c:
            if status == "queued":
                # A newer job for the same key may already be queued; then this retry is redundant.
                await c.execute(
                    "UPDATE jobs SET status = CASE WHEN EXISTS (SELECT 1 FROM jobs j WHERE j.kind = jobs.kind "
                    "AND j.dedupe_key = jobs.dedupe_key AND j.status = 'queued' AND j.id <> jobs.id) THEN 'done' "
                    "ELSE 'queued' END, last_error = %s, run_after = now() + make_interval(secs => %s) WHERE id = %s",
                    (error, delay, job["id"]),
                )
            else:
                await c.execute(
                    "UPDATE jobs SET status = %s, last_error = %s WHERE id = %s", (status, error, job["id"])
                )
        done += 1
    return done
