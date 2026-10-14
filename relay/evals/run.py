"""Run the agent eval suite against the real model.

    uv run python -m evals.run --suite smoke                 # tagged must-pass cases, 1 trial
    uv run python -m evals.run --suite pr --trials 3          # all dev cases: the merge gate
    uv run python -m evals.run --suite release --trials 5     # dev + held-out
    uv run python -m evals.run --suite pr --save runs/main.json
    uv run python -m evals.run --suite pr --baseline runs/main.json
    uv run python -m evals.run --validate                    # check the case files only, no API calls

Every (case, trial) runs in its own Postgres schema, so trials are isolated and run concurrently.
"""

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.agent import run_turn
from app.channels import handle_email
from app.config import settings
from app.db import Store
from app.embeddings import LocalEmbedder, LocalReranker
from app.guardrails import check_reply, sanitize_output
from app.ingest import Doc, reconcile, run_once, sha, sync_document
from app.llm import AnthropicLLM
from app.prompts import system_prompt
from app.quarantine import AnthropicQuarantine
from app.retrieval import Retriever
from app.seed import seed
from app.tools import REGISTRY, Context

from .checks import grade
from .judges import CRITERIA, AnthropicJudge, render
from .simulator import DONE, AnthropicSimulator

NOW = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
CASES = Path(__file__).parent / "cases"
GATES = Path(__file__).parent / "gates.yaml"
KB_SCHEMA = "eval_kb"
KB_COPY = (
    f"INSERT INTO documents SELECT * FROM {KB_SCHEMA}.documents; "
    f"INSERT INTO chunks (chunk_id, doc_id, ord, context, content, embedding, embed_model) "
    f"SELECT chunk_id, doc_id, ord, context, content, embedding, embed_model FROM {KB_SCHEMA}.chunks"
)
EXPECT_KEYS = {
    "must_call",
    "must_not_call",
    "end_state",
    "reply_mentions",
    "reply_not_mentions",
    "refund_at_most",
    "max_steps",
    "judges",
}
MODES = ("input", "turns", "simulator", "email")
SOURCES = {"handwritten", "synthetic-template", "redteam", "redteam-variant", "prod-trace"}
PRICES = {  # USD per million tokens (input, cache write, cache read, output), checked 2026-10-14
    "claude-opus-5-5": (4.00, 5.00, 0.20, 20.00),
    "claude-sonnet-5-5": (2.00, 2.50, 0.10, 10.00),
    "claude-haiku-5-5": (0.10, 0.125, 0.01, 0.50),
}


@dataclass
class Deps:
    llm: object
    models: tuple  # (embedder, reranker)
    quarantine: object
    simulator: object | None = None
    judge: object | None = None


# ---- loading and validation ----------------------------------------------------------------------
def load_cases(suite: str = "pr") -> list[dict]:
    dirs = ["dev"] + (["heldout"] if suite in ("release", "all") else [])
    cases = []
    for d in dirs:
        for path in sorted((CASES / d).glob("*.yaml")):
            for c in yaml.safe_load(path.read_text()) or []:
                cases.append(c | {"split": d})
    if suite == "smoke":
        cases = [c for c in cases if "smoke" in c.get("tags", [])]
    return cases


def validate(cases: list[dict]) -> list[str]:
    errors, ids = [], set()
    for c in cases:
        cid = c.get("id", "?")
        if cid in ids:
            errors.append(f"{cid}: duplicate id")
        ids.add(cid)
        for key in ("id", "category", "source", "env", "expect"):
            if key not in c:
                errors.append(f"{cid}: missing {key}")
        if c.get("source") not in SOURCES:
            errors.append(f"{cid}: source must be one of {sorted(SOURCES)}")
        if sum(m in c for m in MODES) != 1:
            errors.append(f"{cid}: needs exactly one of {MODES}")
        exp = c.get("expect", {})
        for key in set(exp) - EXPECT_KEYS:
            errors.append(f"{cid}: unknown expect key {key}")
        for name in [w["tool"] for w in exp.get("must_call", [])] + exp.get("must_not_call", []):
            if name not in REGISTRY:
                errors.append(f"{cid}: unknown tool {name}")
        for name in exp.get("judges", []):
            if name not in CRITERIA:
                errors.append(f"{cid}: unknown judge {name}")
    return errors


# ---- running one trial ---------------------------------------------------------------------------
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


async def converse(case: dict, ctx: Context, deps: Deps) -> dict:
    """Run the conversation the case describes. Returns replies, transcript, tool calls, usage, steps."""
    out = {
        "replies": [],
        "transcript": [],
        "tool_calls": [],
        "usage": {},
        "max_steps": 0,
        "guard_failures": [],
    }

    def absorb(result) -> None:
        out["tool_calls"] += result.tool_calls
        out["guard_failures"] += result.guard_failures
        out["max_steps"] = max(out["max_steps"], result.steps)
        for k, v in result.usage.items():
            out["usage"][k] = out["usage"].get(k, 0) + v

    if "email" in case:
        outcome = await handle_email(ctx, deps.llm, case["email"].get("subject", ""), case["email"]["body"])
        out["replies"].append(outcome.draft or "")
        out["triage"] = outcome.triage.model_dump()
        if outcome.result:
            absorb(outcome.result)
            out["transcript"] = outcome.result.new_messages
        return out

    history: list[dict] = []
    system = system_prompt([], NOW)
    scripted = case["turns"] if "turns" in case else [case["input"]] if "input" in case else None
    spec = case.get("simulator")
    pairs: list[tuple[str, str]] = []
    for i in range(len(scripted) if scripted else spec.get("max_turns", 6)):
        if scripted:
            message = scripted[i]
        else:
            message = await deps.simulator.next_message(spec, pairs)
            if message.strip() == DONE:
                break
        chunks: list[str] = []

        async def collect(t: str, chunks=chunks) -> None:
            chunks.append(sanitize_output(t))

        user = {"role": "user", "content": [{"type": "text", "text": message.replace(DONE, "").strip()}]}
        ctx.retrieved = set()
        result = await run_turn(
            ctx,
            deps.llm,
            system,
            [*history, user],
            collect,
            guard=lambda d, r: check_reply(d, ctx.retrieved, r.tool_calls),
        )
        absorb(result)
        history += [user, *result.new_messages]
        reply = "".join(chunks)
        out["replies"].append(reply)
        pairs.append((message, reply))
        if spec and DONE in message:
            break
    out["transcript"] = history
    return out


async def run_one(case: dict, trial: int, deps: Deps, sem: asyncio.Semaphore) -> dict:
    base = {"id": case["id"], "category": case["category"], "source": case.get("source"), "trial": trial}
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
            for d in case["env"].get("kb_extra", []):  # e.g. a poisoned document for red-team cases
                body = d["body"]
                doc = Doc(
                    d["doc_id"],
                    d.get("title", d["doc_id"]),
                    d.get("acl", ["public"]),
                    body,
                    sha(body),
                    "eval",
                )
                await sync_document(store, deps.models[0], doc)
            await seed(store, case["env"], NOW)
            ctx = Context(
                store=store,
                customer_id=case["env"]["customer_id"],
                session_id=None,
                now=NOW,
                retriever=Retriever(store, *deps.models),
                quarantine=deps.quarantine,
            )
            t0 = time.perf_counter()
            conv = await converse(case, ctx, deps)
            latency = time.perf_counter() - t0
            reply = "\n".join(conv["replies"])
            fails = grade(case["expect"], reply, conv["tool_calls"], await snapshot(store), conv["max_steps"])
            verdicts = {}
            for name in case["expect"].get("judges", []):
                if deps.judge is None:
                    continue
                v = await deps.judge.judge(name, render(conv["transcript"]))
                verdicts[name] = v.model_dump()
                if v.verdict == "fail":
                    fails.append(f"judge {name}: {v.reasoning[:120]}")
            return base | {
                "pass": not fails,
                "fails": fails,
                "steps": conv["max_steps"],
                "usage": conv["usage"],
                "latency_s": round(latency, 2),
                "reply": reply,
                "tool_calls": conv["tool_calls"],
                "guard_failures": conv["guard_failures"],
                "judges": verdicts,
                "transcript": conv["transcript"],
            }
        except Exception as e:  # noqa: BLE001 - a crash is a failed trial, not a crashed suite
            return base | {
                "pass": False,
                "fails": [f"error: {e!r}"],
                "steps": 0,
                "usage": {},
                "latency_s": 0.0,
            }
        finally:
            await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            await conn.close()


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


# ---- reporting and gates -------------------------------------------------------------------------
def regression_p(regressions: int, improvements: int) -> float:
    """Exact one-sided McNemar test: P(at least this many regressions among flips | no real change)."""
    n = regressions + improvements
    if n == 0:
        return 1.0
    return sum(math.comb(n, i) for i in range(regressions, n + 1)) / 2**n


def evaluate_gates(results: list[dict], gates: dict, model: str, baseline: dict | None) -> list[str]:
    failures = []
    bad = sorted(
        {r["id"] for r in results if r["category"] in gates["must_never"]["categories"] and not r["pass"]}
    )
    if bad:
        failures.append(f"must-never cases failed: {bad}")
    by_cat: dict[str, list[bool]] = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r["pass"])
    for cat, floor in gates.get("min_pass_rate", {}).items():
        if cat in by_cat and (rate := sum(by_cat[cat]) / len(by_cat[cat])) < floor:
            failures.append(f"{cat} pass rate {rate:.1%} < {floor:.0%}")
    overall = sum(r["pass"] for r in results) / len(results)
    if overall < gates.get("overall_min_pass_rate", 0):
        failures.append(f"overall pass rate {overall:.1%} < {gates['overall_min_pass_rate']:.0%}")
    budgets = gates.get("budgets", {})
    lat = sorted(r["latency_s"] for r in results)
    p95 = lat[math.ceil(0.95 * len(lat)) - 1]
    if "p95_latency_s" in budgets and p95 > budgets["p95_latency_s"]:
        failures.append(f"p95 latency {p95:.1f} s > {budgets['p95_latency_s']} s")
    mean_cost = statistics.mean(cost(r["usage"], model) for r in results)
    if "mean_cost_per_trial_usd" in budgets and mean_cost > budgets["mean_cost_per_trial_usd"]:
        failures.append(f"mean cost ${mean_cost:.4f} > ${budgets['mean_cost_per_trial_usd']}")
    if baseline:
        base = {(r["id"], r["trial"]): r["pass"] for r in baseline["results"]}
        b = sum(1 for r in results if base.get((r["id"], r["trial"])) is True and not r["pass"])
        c = sum(1 for r in results if base.get((r["id"], r["trial"])) is False and r["pass"])
        p = regression_p(b, c)
        print(f"vs baseline: {b} regressions, {c} improvements, p = {p:.3f}")
        if b > c and p < gates.get("max_regression_p", 0.05):
            failures.append(f"significant regression vs baseline ({b} vs {c}, p = {p:.3f})")
    return failures


def report(results: list[dict], trials: int, model: str) -> None:
    by_case: dict[str, list[dict]] = {}
    for r in results:
        by_case.setdefault(r["id"], []).append(r)
    print(f"\n{'case':40} {'pass':>5} {'steps':>5} {'tokens':>8} {'p95_s':>6}  failures")
    for cid, rs in by_case.items():
        passed = sum(r["pass"] for r in rs)
        tokens = statistics.mean(sum(r["usage"].values()) for r in rs)
        p95 = sorted(r["latency_s"] for r in rs)[max(0, math.ceil(0.95 * len(rs)) - 1)]
        note = "; ".join(sorted({f for r in rs for f in r["fails"]}))[:90]
        print(
            f"{cid:40} {passed}/{len(rs):<3} {statistics.mean(r['steps'] for r in rs):>5.1f} {tokens:>8,.0f} "
            f"{p95:>6.1f}  {note}"
        )
    total, passed = len(results), sum(r["pass"] for r in results)
    pass_k = sum(all(r["pass"] for r in rs) for rs in by_case.values())
    spend = sum(cost(r["usage"], model) for r in results)
    print(
        f"\noverall: {passed}/{total} trials ({passed / total:.1%}), pass^{trials} = {pass_k}/{len(by_case)} cases, "
        f"cost ${spend:.2f} on {model}"
    )
    cats: dict[str, list[bool]] = {}
    for r in results:
        cats.setdefault(r["category"], []).append(r["pass"])
    print("by category: " + ", ".join(f"{k} {sum(v)}/{len(v)}" for k, v in sorted(cats.items())))


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=["smoke", "pr", "release", "all"], default="pr")
    ap.add_argument("--trials", type=int)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--only", help="run cases whose id contains this text")
    ap.add_argument("--no-judges", action="store_true")
    ap.add_argument("--save")
    ap.add_argument("--baseline")
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()

    all_cases = load_cases("all")
    errors = validate(all_cases)
    if errors or args.validate:
        print("\n".join(errors) or f"{len(all_cases)} cases OK")
        return 1 if errors else 0
    cases = load_cases(args.suite)
    if args.only:
        cases = [c for c in cases if args.only in c["id"]]
    trials = args.trials or {"smoke": 1, "pr": 3, "release": 5, "all": 3}[args.suite]

    models = (LocalEmbedder(), LocalReranker())
    await build_kb(models[0])
    deps = Deps(
        llm=AnthropicLLM(settings.model, settings.max_tokens, settings.refusal_fallback),
        models=models,
        quarantine=AnthropicQuarantine(settings.memory_model),
        simulator=AnthropicSimulator(settings.memory_model),
        judge=None if args.no_judges else AnthropicJudge(settings.judge_model),
    )
    sem = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(*(run_one(c, t, deps, sem) for c in cases for t in range(trials)))
    report(results, trials, settings.model)
    baseline = json.loads(Path(args.baseline).read_text()) if args.baseline else None
    failures = evaluate_gates(results, yaml.safe_load(GATES.read_text()), settings.model, baseline)
    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(
            json.dumps(
                {"model": settings.model, "suite": args.suite, "results": results}, indent=1, default=str
            )
        )
    print("\nGATE " + ("PASSED" if not failures else "FAILED:\n  " + "\n  ".join(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
