"""The behavioural eval runner: scoring, gates, and one real case run through the platform."""

from pathlib import Path

import yaml

from helpdesk.evals import gate, run_case
from tests.harness import USER_SECRET
from tests.provider import calls

CASES = Path(__file__).parents[1] / "evals" / "cases"


def test_every_suite_parses_and_names_known_agents_and_tools():
    from helpdesk.servers.systems import Store, all_servers

    tools = {f"{slug}__{t}" for slug, s in all_servers(Store()).items() for t in s.tools}
    agents = {"emp-triage", "it-access", "hr-policy", "cust-triage", "billing", "returns"}
    for path in CASES.glob("*.yaml"):
        for case in yaml.safe_load(path.read_text()):
            expect = case["expect"]
            assert case["tenant"] in ("employee", "customer") and case["message"], case["id"]
            assert expect.get("route", "it-access") in agents, case["id"]
            assert set(expect.get("must_call", []) + expect.get("must_not_call", [])) <= tools, case["id"]


def test_gates_fail_on_any_must_never_miss():
    report = {
        "suite": "billing",
        "pass_hat_k": 0.95,
        "results": [{"id": "x", "category": "injection", "passed": 2, "trials": 3}],
    }
    assert gate(report, {"must_never": ["injection"]}) == ["billing/x: must-never category injection failed"]
    assert gate(report | {"results": []}, {"default_min_pass_hat_k": 0.99}) == ["billing: pass^k 0.95 below 0.99"]


async def test_a_case_runs_through_the_platform_and_is_scored_from_the_trace(platform):
    case = next(c for c in yaml.safe_load((CASES / "it-access.yaml").read_text()) if c["id"] == "unlock-own-account")
    platform.script(
        emp_triage=[calls(("handoff", {"to": "it-access", "summary": "locked out"}))],
        it_access=[
            calls(("idp__unlock_account", {"user_id": "{user}"})),
            calls(("ticketing__resolve_ticket", {"ticket_id": "{ticket}", "resolution": "unlocked"})),
            "Your account is unlocked.",
        ],
    )
    assert await run_case(platform.http, USER_SECRET, case) == []
    platform.script(emp_triage=["Hello, what do you need?"])
    failures = await run_case(platform.http, USER_SECRET, case)
    assert any(f.startswith("route:") for f in failures) and any("must_call" in f for f in failures)
