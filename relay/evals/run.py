"""Run the eval suite against the real model.

    uv run python -m evals.run                      # 25 cases x 3 trials
    uv run python -m evals.run --trials 1 --only refund
    uv run python -m evals.run --save runs/main.json
    uv run python -m evals.run --baseline runs/main.json
    uv run python -m evals.run --validate           # check the case file only, no API calls

Every (case, trial) runs in its own Postgres schema, so runs are isolated and can execute concurrently.
"""

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.agent import run_turn
from app.config import settings
from app.db import Store
from app.embeddings import LocalEmbedder, LocalReranker
from app.guardrails import check_reply
from app.ingest import reconcile, run_once
from app.llm import AnthropicLLM
from app.prompts import system_prompt
from app.retrieval import Retriever
from app.seed import seed
from app.tools import REGISTRY, Context

KB_SCHEMA = "eval_kb"
KB_COPY = (
    f"INSERT INTO documents SELECT * FROM {KB_SCHEMA}.documents; "
    f"INSERT INTO chunks (chunk_id, doc_id, ord, context, content, embedding, embed_model) "
    f"SELECT chunk_id, doc_id, ord, context, content, embedding, embed_model FROM {KB_SCHEMA}.chunks"
)

from .checks import grade

NOW = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
CASES = Path(__file__).parent / "cases.yaml"
EXPECT_KEYS = {
    "must_call",
    "must_not_call",
    "end_state",
    "reply_mentions",
    "reply_not_mentions",
    "refund_at_most",
    "max_steps",
}
PRICES = {  # USD per million tokens (input, cache write, cache read, output), checked 2026-10-14
    "claude-opus-5-5": (4.00, 5.00, 0.20, 20.00),
    "claude-sonnet-5-5": (2.00, 2.50, 0.10, 10.00),
    "claude-haiku-5-5": (0.10, 0.125, 0.01, 0.50),
}


def validate(cases: list[dict]) -> list[str]:
    errors, ids = [], set()
    for c in cases:
        cid = c.get("id", "?")
        if cid in ids:
            errors.append(f"{cid}: duplicate id")
        ids.add(cid)
        for key in ("id", "category", "env", "input", "expect"):
            if key not in c:
                errors.append(f"{cid}: missing {key}")
        for key in set(c.get("expect", {})) - EXPECT_KEYS:
            errors.append(f"{cid}: unknown expect key {key}")
        for want in c.get("expect", {}).get("must_call", []):
            if want["tool"] not in REGISTRY:
                errors.append(f"{cid}: unknown tool {want['tool']}")
        for name in c.get("expect", {}).get("must_not_call", []):
            if name not in REGISTRY:
                errors.append(f"{cid}: unknown tool {name}")
    return errors


async def snapshot(store: Store) -> dict:
    async with store.conn() as c:
        refunds = await (await c.execute("SELECT order_id, amount FROM refunds")).fetchall()
        approvals = await (await c.execute("SELECT order_id, amount FROM approvals")).fetchall()
        escalations = await (await c.execute("SELECT reason FROM escalations")).fetchall()
    return {"refunds": refunds, "approvals": approvals, "escalations": escalations}


def cost(usage: dict, model: str) -> float:
    p_in, p_write, p_read, p_out = PRICES.get(model, (0, 0, 0, 0))
    return (
        usage.get("input_tokens", 0) * p_in
        + usage.get("cache_creation_input_tokens", 0) * p_write
        + usage.get("cache_read_input_tokens", 0) * p_read
        + usage.get("output_tokens", 0) * p_out
    ) / 1e6


async def run_one(case: dict, trial: int, llm, sem: asyncio.Semaphore, models: tuple) -> dict:
    async with sem:
        conn = await AsyncConnection.connect(settings.database_url, autocommit=True, row_factory=dict_row)
        schema = f"eval_{uuid4().hex[:12]}"
        try:
            await conn.execute(f"CREATE SCHEMA {schema}")
            await conn.execute(f"SET search_path TO {schema}, public")
            store = Store(conn)
            await store.apply_schema()
            await conn.execute(
                KB_COPY
            )  # the indexed knowledge base, copied rather than re-embedded per trial
            await seed(store, case["env"], NOW)
            ctx = Context(
                store=store,
                customer_id=case["env"]["customer_id"],
                session_id=None,
                now=NOW,
                retriever=Retriever(store, *models),
            )
            chunks: list[str] = []

            async def on_text(t):
                chunks.append(t)

            t0 = time.perf_counter()
            history = [{"role": "user", "content": [{"type": "text", "text": case["input"]}]}]
            result = await run_turn(
                ctx,
                llm,
                system_prompt([], NOW),
                history,
                on_text,
                guard=lambda d, r: check_reply(d, ctx.retrieved, r.tool_calls),
            )
            latency = time.perf_counter() - t0
            reply = "".join(chunks)
            fails = grade(case["expect"], reply, result.tool_calls, await snapshot(store), result.steps)
            return {
                "id": case["id"],
                "category": case["category"],
                "trial": trial,
                "pass": not fails,
                "fails": fails,
                "steps": result.steps,
                "guard_failures": result.guard_failures,
                "usage": dict(result.usage),
                "latency_s": round(latency, 2),
                "reply": reply,
                "tool_calls": result.tool_calls,
                "transcript": history + result.new_messages,
            }
        except Exception as e:  # noqa: BLE001 - a crash is a failed trial, not a crashed suite
            return {
                "id": case["id"],
                "category": case["category"],
                "trial": trial,
                "pass": False,
                "fails": [f"error: {e!r}"],
                "steps": 0,
                "usage": {},
                "latency_s": 0.0,
            }
        finally:
            await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            await conn.close()


def report(results: list[dict], trials: int, model: str, baseline: dict | None) -> bool:
    by_case: dict[str, list[dict]] = {}
    for r in results:
        by_case.setdefault(r["id"], []).append(r)
    print(f"\n{'case':38} {'pass':>5} {'steps':>5} {'tokens':>8} {'p95_s':>6}  failures")
    for cid, rs in by_case.items():
        passed = sum(r["pass"] for r in rs)
        tokens = statistics.mean(sum(r["usage"].values()) for r in rs) if rs else 0
        p95 = sorted(r["latency_s"] for r in rs)[max(0, math.ceil(0.95 * len(rs)) - 1)]
        note = "; ".join(sorted({f for r in rs for f in r["fails"]}))[:90]
        print(
            f"{cid:38} {passed}/{len(rs):<3} {statistics.mean(r['steps'] for r in rs):>5.1f} {tokens:>8,.0f} {p95:>6.1f}  {note}"
        )
    total = len(results)
    passed = sum(r["pass"] for r in results)
    pass_k = sum(all(r["pass"] for r in rs) for rs in by_case.values())
    lat = sorted(r["latency_s"] for r in results)
    spend = sum(cost(r["usage"], model) for r in results)
    print(
        f"\noverall: {passed}/{total} trials ({passed / total:.1%}), pass^{trials} = {pass_k}/{len(by_case)} cases, "
        f"p95 latency {lat[math.ceil(0.95 * len(lat)) - 1]:.1f} s, cost ${spend:.2f} on {model}"
    )
    cats: dict[str, list[bool]] = {}
    for r in results:
        cats.setdefault(r["category"], []).append(r["pass"])
    print("by category: " + ", ".join(f"{k} {sum(v)}/{len(v)}" for k, v in sorted(cats.items())))

    must_never = [r for r in results if r["category"] in ("cross_customer", "injection") and not r["pass"]]
    if baseline:
        base = {(r["id"], r["trial"]): r["pass"] for r in baseline["results"]}
        b = sum(1 for r in results if base.get((r["id"], r["trial"])) is True and not r["pass"])
        c = sum(1 for r in results if base.get((r["id"], r["trial"])) is False and r["pass"])
        print(f"vs baseline: {b} regressions, {c} improvements")
    if must_never:
        print(f"MUST-NEVER GATE FAILED: {sorted({r['id'] for r in must_never})}")
    return not must_never


async def build_kb(embedder) -> None:
    """Index kb/ once into a shared schema that every trial copies from."""
    conn = await AsyncConnection.connect(settings.database_url, autocommit=True, row_factory=dict_row)
    await conn.execute(f"DROP SCHEMA IF EXISTS {KB_SCHEMA} CASCADE")
    await conn.execute(f"CREATE SCHEMA {KB_SCHEMA}")
    await conn.execute(f"SET search_path TO {KB_SCHEMA}, public")
    store = Store(conn)
    await store.apply_schema()
    await reconcile(store)
    await run_once(store, embedder)
    await conn.close()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--only", help="run cases whose id contains this text")
    ap.add_argument("--save")
    ap.add_argument("--baseline")
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()

    cases = yaml.safe_load(CASES.read_text())
    errors = validate(cases)
    if errors or args.validate:
        print("\n".join(errors) or f"{len(cases)} cases OK")
        return 1 if errors else 0
    if args.only:
        cases = [c for c in cases if args.only in c["id"]]

    models = (LocalEmbedder(), LocalReranker())
    await build_kb(models[0])
    llm = AnthropicLLM(settings.model, settings.max_tokens, settings.refusal_fallback)
    sem = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(
        *(run_one(c, t, llm, sem, models) for c in cases for t in range(args.trials))
    )
    baseline = json.loads(Path(args.baseline).read_text()) if args.baseline else None
    gate_ok = report(results, args.trials, settings.model, baseline)
    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(
            json.dumps({"model": settings.model, "results": results}, indent=1, default=str)
        )
    return 0 if gate_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
