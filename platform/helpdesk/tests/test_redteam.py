"""The red-team suites (evals/redteam/*.yaml), with the model assumed fully compromised: every scripted attack runs
through the real platform, and the checks are on outcomes. See evals/redteam/README.md."""

from pathlib import Path

import pytest
import yaml

from tests.provider import calls

SUITES = Path(__file__).parents[1] / "evals" / "redteam"
CASES = [(f.stem, c) for f in sorted(SUITES.glob("*.yaml")) for c in yaml.safe_load(f.read_text())]
TRIAGE = {"employee": "emp-triage", "customer": "cust-triage"}


def at(store, path: str):
    head, *rest = path.split(".")
    node = getattr(store, head)
    for key in rest:
        node = node[tuple(key.split("/"))] if "/" in key else node[key]
    return node


@pytest.mark.parametrize(("suite", "case"), CASES, ids=[f"{s}/{c['id']}" for s, c in CASES])
async def test_attack_fails(platform, suite, case):
    platform.store.tickets[("employee", "T-employee")] = {
        "notes": [{"by": "it", "note": "employee-secret"}],
        "resolution": None,
    }
    platform.store.tickets[("customer", "T-customer")] = {
        "notes": [{"by": "billing", "note": "customer-secret"}],
        "resolution": None,
    }
    triage, agent = TRIAGE[case["tenant"]], case["agent"]
    attack = [calls(*[(tool, args) for tool, args in turn]) for turn in case["attack"]] + ["done"]
    if agent == triage:
        platform.script(**{triage: attack})
    else:
        platform.script(**{triage: [calls(("handoff", {"to": agent, "summary": case["message"]}))], agent: attack})

    who = platform.user(case["user"], case["tenant"], *case.get("roles", ["staff"]))
    ticket = await platform.open(who, case["message"])
    trace = await platform.trace(ticket["id"], platform.user("rt-sup", case["tenant"], "supervisor"))
    expect = case["expect"]

    for path, want in (expect.get("state") or {}).items():
        assert at(platform.store, path) == want, f"{path} changed"
    tool_events = [e["detail"] for e in trace["events"] if e["kind"] == "tool_call"]
    for tool, allowed in (expect.get("outcomes") or {}).items():
        seen = [e["outcome"] for e in tool_events if e["tool"] == tool] or ["unlisted"]
        assert set(seen) <= set(allowed), f"{tool}: {seen} not in {allowed}"
    for tool, flags in (expect.get("flags") or {}).items():
        found = {f for e in tool_events if e["tool"] == tool for f in e["flags"]}
        assert set(flags) <= found, f"{tool}: flags {found}"
    for text in expect.get("never_in_trace", []):
        assert text not in str(trace), f"{text!r} leaked into the trace"
    if "status" in expect:
        assert trace["ticket"]["status"] == expect["status"]
