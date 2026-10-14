"""Measure retrieval on its own: recall@k and MRR per search mode, plus an access-control leak check.

uv run python -m evals.retrieval            # local models (downloaded on first run), no API key needed
uv run python -m evals.retrieval --k 6
"""

import argparse
import asyncio
import statistics
import tempfile
import time
from pathlib import Path

import pgserver
import yaml
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.db import Store
from app.embeddings import LocalEmbedder, LocalReranker
from app.ingest import reconcile, run_once
from app.retrieval import Retriever, principals_for

QUERIES = Path(__file__).parent / "retrieval.yaml"
MODES = ["lexical", "vector", "hybrid", "hybrid+rerank"]


def unique_docs(hits) -> list[str]:
    return list(dict.fromkeys(h.doc_id for h in hits))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=6)
    args = ap.parse_args()

    srv = pgserver.get_server(tempfile.mkdtemp(), cleanup_mode="stop")
    srv.psql("CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;")
    conn = await AsyncConnection.connect(srv.get_uri(), autocommit=True, row_factory=dict_row)
    store = Store(conn)
    await store.apply_schema()
    embedder = LocalEmbedder()
    t0 = time.perf_counter()
    await reconcile(store)
    await run_once(store, embedder)
    print(f"indexed kb/ in {time.perf_counter() - t0:.1f} s with {embedder.name}")
    retriever = Retriever(store, embedder, LocalReranker())

    queries = yaml.safe_load(QUERIES.read_text())
    print(
        f"\n{len(queries)} queries, k={args.k}\n{'mode':15} {'recall@k':>9} {'MRR':>6} {'p50 ms':>7} {'leaks':>6}"
    )
    for mode in MODES:
        recalls, rrs, times, leaks = [], [], [], 0
        for item in queries:
            staff = item.get("who") == "staff"
            t = time.perf_counter()
            docs = unique_docs(
                await retriever.search(item["q"], principals_for("eval", staff), k=args.k * 2, mode=mode)
            )[: args.k]
            times.append((time.perf_counter() - t) * 1000)
            relevant = set(item["relevant"])
            recalls.append(len(relevant & set(docs)) / len(relevant))
            rank = next((i for i, d in enumerate(docs, 1) if d in relevant), None)
            rrs.append(1 / rank if rank else 0.0)
            leaks += sum(d.startswith("INT-") for d in docs) if not staff else 0
        print(
            f"{mode:15} {statistics.mean(recalls):>9.3f} {statistics.mean(rrs):>6.3f} "
            f"{statistics.median(times):>7.0f} {leaks:>6}"
        )
    await conn.close()
    srv.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
