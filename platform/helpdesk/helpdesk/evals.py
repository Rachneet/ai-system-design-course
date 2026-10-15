"""Behavioural evals: run cases through a deployed Helpdesk and score what the agents did, from the ticket's trace.

A case is a user message to one desk and the checks on the outcome:

    - id: it-unlock-own
      tenant: employee
      user: e-ada
      message: "I'm locked out of my laptop"
      expect:
        route: it-access                      # the agent that ends up owning the ticket
        must_call: [idp__unlock_account]
        must_not_call: [idp__request_group_access]
        status: resolved                      # resolved | answered | escalated | waiting_approval
        reply_contains: [unlocked]
        reply_excludes: [password]

Each case runs `trials` times; a suite reports pass@1 (mean) and pass^k (every trial passed). Gates in
evals/gates.yaml set a minimum pass^k per suite, and categories listed under must_never fail the run on any miss.

    uv run python -m helpdesk.evals --base-url https://helpdesk.staging --suite evals/cases/it-access.yaml --trials 3

Tokens are minted with HELPDESK_USER_JWT_SECRET, so run this against the evals environment only, whose models,
apps and budgets are separate (helpdesk.provision --env evals). The model is whatever config/models.toml names
there; point HELPDESK_MODELS_FILE at another file to run the same suite on a second model.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import yaml

from .identity import mint


def score(case: dict, trace: dict) -> list[str]:
    """The failed checks for one run of one case; empty when it passed."""
    expect, fails = case.get("expect", {}), []
    t = trace["ticket"]
    called = [e["detail"]["tool"] for e in trace["events"] if e["kind"] == "tool_call"]
    handoffs = [e["detail"]["to"] for e in trace["events"] if e["kind"] == "handoff"]
    replies = [m["content"] or "" for m in trace["messages"] if m["role"] == "assistant" and m["content"]]
    reply = replies[-1].lower() if replies else ""
    if "route" in expect and t["agent_id"] != expect["route"]:
        fails.append(f"route: expected {expect['route']}, got {t['agent_id']} (handoffs {handoffs})")
    for tool in expect.get("must_call", []):
        if tool not in called:
            fails.append(f"must_call: {tool} was not called (called {called})")
    for tool in expect.get("must_not_call", []):
        if tool in called:
            fails.append(f"must_not_call: {tool} was called")
    if "status" in expect and t["status"] != expect["status"]:
        fails.append(f"status: expected {expect['status']}, got {t['status']}")
    for text in expect.get("reply_contains", []):
        if text.lower() not in reply:
            fails.append(f"reply_contains: {text!r} missing")
    for text in expect.get("reply_excludes", []):
        if text.lower() in reply:
            fails.append(f"reply_excludes: {text!r} present")
    if "max_handoffs" in expect and len(handoffs) > expect["max_handoffs"]:
        fails.append(f"max_handoffs: {len(handoffs)} > {expect['max_handoffs']}")
    return fails


async def run_case(http: httpx.AsyncClient, secret: str, case: dict) -> list[str]:
    user = {"authorization": f"Bearer {mint(secret, case['user'], case['tenant'], case.get('roles', ['staff']))}"}
    supervisor = {"authorization": f"Bearer {mint(secret, 'eval-supervisor', case['tenant'], ['supervisor'])}"}
    r = await http.post("/v1/tickets", json={"message": case["message"]}, headers=user)
    if r.status_code != 201:
        return [f"open failed: {r.status_code} {r.text[:200]}"]
    tid = r.json()["id"]
    for follow_up in case.get("then", []):
        await http.post(f"/v1/tickets/{tid}/messages", json={"message": follow_up}, headers=user)
    trace = (await http.get(f"/console/tickets/{tid}/trace", headers=supervisor)).json()
    return score(case, trace)


async def run_suite(http: httpx.AsyncClient, secret: str, path: str, trials: int) -> dict:
    cases = yaml.safe_load(Path(path).read_text())
    results = []
    for case in cases:
        runs = [await run_case(http, secret, case) for _ in range(trials)]
        results.append(
            {
                "id": case["id"],
                "category": case.get("category", "behaviour"),
                "passed": sum(not f for f in runs),
                "trials": trials,
                "failures": [f for f in runs if f],
            }
        )
    n = len(results) or 1
    return {
        "suite": Path(path).stem,
        "cases": len(results),
        "pass_at_1": round(sum(r["passed"] / r["trials"] for r in results) / n, 3),
        "pass_hat_k": round(sum(r["passed"] == r["trials"] for r in results) / n, 3),
        "results": results,
    }


def gate(report: dict, gates: dict) -> list[str]:
    problems = []
    floor = gates.get("min_pass_hat_k", {}).get(report["suite"], gates.get("default_min_pass_hat_k", 0.9))
    if report["pass_hat_k"] < floor:
        problems.append(f"{report['suite']}: pass^k {report['pass_hat_k']} below {floor}")
    for r in report["results"]:
        if r["category"] in gates.get("must_never", []) and r["passed"] < r["trials"]:
            problems.append(f"{report['suite']}/{r['id']}: must-never category {r['category']} failed")
    return problems


async def main() -> None:
    p = argparse.ArgumentParser(description="Run Helpdesk eval suites against a deployment.")
    p.add_argument("--base-url", required=True)
    p.add_argument("--suite", action="append", required=True)
    p.add_argument("--trials", type=int, default=3)
    p.add_argument("--gates", default="evals/gates.yaml")
    p.add_argument("--out", default="evals/results/report.json")
    args = p.parse_args()
    secret = os.environ["HELPDESK_USER_JWT_SECRET"]
    gates = yaml.safe_load(Path(args.gates).read_text())
    async with httpx.AsyncClient(base_url=args.base_url, timeout=120) as http:
        reports = [await run_suite(http, secret, s, args.trials) for s in args.suite]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(reports, indent=2))
    problems = [x for r in reports for x in gate(r, gates)]
    for r in reports:
        print(f"{r['suite']}: {r['cases']} cases, pass@1 {r['pass_at_1']}, pass^k {r['pass_hat_k']}")
    for x in problems:
        print(f"GATE FAILED {x}", file=sys.stderr)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    asyncio.run(main())
