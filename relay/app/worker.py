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

from .config import settings
from .db import Store, open_pool
from .ingest import reconcile, run_once
from .jobs import run_ready
from .memory import remember
from .wiring import build_embedder, build_extractor

log = logging.getLogger("relay.worker")


async def health_server(port: int) -> asyncio.base_events.Server:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readline()
        writer.write(
            b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 11\r\n\r\n{"ok":true}'
        )
        await writer.drain()
        writer.close()

    return await asyncio.start_server(handle, "0.0.0.0", port)


def handlers(store: Store, extractor) -> dict:
    async def extract_memory(payload: dict) -> None:
        session_id = UUID(payload["session_id"])
        messages = await store.load_session(session_id, payload["customer_id"])
        await remember(store, extractor, payload["customer_id"], session_id, messages)

    return {"extract_memory": extract_memory}


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    pool = await open_pool(settings.database_url, max_size=4)
    store = Store(pool)
    await store.apply_schema()
    embedder, extractor = build_embedder(), build_extractor()
    server = await health_server(int(os.environ.get("PORT", "8081")))
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    jobs = handlers(store, extractor)
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
