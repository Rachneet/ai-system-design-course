"""Background worker: knowledge-base ingestion and memory extraction, outside the request path.

    uv run python -m app.worker

Serves GET /healthz on $PORT so platforms that require an HTTP port (such as Cloud Run services) can probe it.
"""

import asyncio
import contextlib
import logging
import os
import signal
from uuid import UUID

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import online
from .config import settings
from .db import Store, open_pool
from .ingest import reconcile, run_once
from .jobs import run_ready
from .memory import remember
from .telemetry import setup as setup_tracing
from .wiring import build_embedder, build_extractor, build_judge

log = logging.getLogger("relay.worker")


async def health_server(port: int) -> asyncio.base_events.Server:
    """GET /healthz for probes, GET /metrics for Prometheus. Deliberately tiny: no framework needed."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_line = (await reader.readline()).decode(errors="replace")
        if " /metrics" in request_line:
            body, ctype = generate_latest(), CONTENT_TYPE_LATEST.encode()
        else:
            body, ctype = b'{"ok":true}', b"application/json"
        head = (
            b"HTTP/1.1 200 OK\r\nContent-Type: " + ctype + b"\r\nContent-Length: " + str(len(body)).encode()
        )
        writer.write(head + b"\r\nConnection: close\r\n\r\n" + body)
        await writer.drain()
        writer.close()

    return await asyncio.start_server(handle, "0.0.0.0", port)


def handlers(store: Store, extractor, judge=None) -> dict:
    async def extract_memory(payload: dict) -> None:
        session_id = UUID(payload["session_id"])
        messages = await store.load_session(session_id, payload["customer_id"])
        await remember(store, extractor, payload["customer_id"], session_id, messages)

    async def judge_session(payload: dict) -> None:
        if judge is not None:
            await online.judge_session(store, judge, payload)

    return {"extract_memory": extract_memory, "judge_session": judge_session}


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    setup_tracing("relay-worker")
    pool = await open_pool(settings.database_url, max_size=4)
    store = Store(pool)
    await store.apply_schema()
    embedder, extractor = build_embedder(), build_extractor()
    server = await health_server(int(os.environ.get("PORT", "8081")))
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    jobs = handlers(store, extractor, build_judge())
    reconcile_every, since_reconcile = 300, 300
    while not stop.is_set():
        if since_reconcile >= reconcile_every:  # the safety net for missed change events
            await reconcile(store)
            since_reconcile = 0
        done = await run_once(store, embedder) + await run_ready(store, jobs)
        if not done:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=1.0)
            since_reconcile += 1
    log.info("shutting down")  # in-flight jobs finished above; queued ones stay queued for the next worker
    server.close()
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
