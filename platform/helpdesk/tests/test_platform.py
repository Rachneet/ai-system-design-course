"""Helpdesk OS end to end on the real platform: every model call through Switchboard, every tool call through
Checkpoint, every server, agent and skill approved in Atlas. Only the model is scripted."""

from tests import provider
from tests.provider import calls

ADA = ("e-ada", "employee")
ANA = ("c-ana", "customer")


async def test_account_unlock_end_to_end(platform):
    platform.script(
        emp_triage=[calls(("handoff", {"to": "it-access", "summary": "e-ada is locked out of their laptop"}))],
        it_access=[
            calls(("idp__get_account", {"user_id": "{user}"})),
            calls(("idp__unlock_account", {"user_id": "{user}"})),
            calls(("ticketing__resolve_ticket", {"ticket_id": "{ticket}", "resolution": "unlocked own account"})),
            "Your account is unlocked. You can sign in again.",
        ],
    )
    ticket = await platform.open(platform.user(*ADA), "I'm locked out of my laptop")
    assert ticket["status"] == "resolved" and ticket["agent_id"] == "it-access"
    assert ticket["messages"][-1]["text"].startswith("Your account is unlocked")
    assert platform.store.accounts["e-ada"]["locked"] is False

    # No provider key or tool credential in the agent: Switchboard's key went to the provider, the agent's key did not.
    assert set(provider.state["keys"]) == {"Bearer provider-secret"}
    trace = await platform.trace(ticket["id"], platform.user("e-sup", "employee", "supervisor"))
    kinds = [e["kind"] for e in trace["events"]]
    assert kinds.count("model_call") == 5 and kinds.count("tool_call") == 3 and "handoff" in kinds
    assert all(e["detail"]["request_id"].startswith("sbr_") for e in trace["events"] if e["kind"] == "model_call")
    # Every tool call is in Checkpoint's decision log with the policy that allowed it.
    log = await platform.decisions(tenant="employee")
    assert sorted((d["tool"], d["decision"], tuple(d["policies"])) for d in log) == [
        ("idp__get_account", "allow", ("it-own-account",)),
        ("idp__unlock_account", "allow", ("it-own-account",)),
        ("ticketing__resolve_ticket", "allow", ("acting-specialists-write-tickets",)),
    ]


async def test_unlocking_someone_elses_account_is_refused_twice_over(platform):
    platform.script(
        emp_triage=[calls(("handoff", {"to": "it-access", "summary": "unlock e-cy"}))],
        it_access=[calls(("idp__unlock_account", {"user_id": "e-cy"})), "I can only unlock your own account."],
    )
    ticket = await platform.open(platform.user("e-bo", "employee"), "Unlock my colleague e-cy, they asked me to")
    assert platform.store.accounts["e-cy"]["locked"] is True
    [d] = await platform.decisions(tenant="employee")
    assert (d["tool"], d["decision"]) == ("idp__unlock_account", "deny")
    assert ticket["status"] == "answered"


async def test_a_large_refund_is_held_approved_by_a_second_person_and_runs_once(platform):
    platform.script(
        cust_triage=[calls(("handoff", {"to": "billing", "summary": "refund for broken chair O-1002"}))],
        billing=[
            calls(("orders__refund", {"order_id": "O-1002", "amount_cents": 18000, "reason": "arrived broken"})),
            calls(("ticketing__resolve_ticket", {"ticket_id": "{ticket}", "resolution": "refunded 180 EUR"})),
            "Refunded 180.00 EUR to your card; it arrives within 5 working days.",
        ],
    )
    ana = platform.user(*ANA)
    ticket = await platform.open(ana, "My chair O-1002 arrived broken, please refund it")
    assert ticket["status"] == "waiting_approval" and platform.store.orders["O-1002"]["refunded_cents"] == 0

    lead = platform.user("c-lead", "customer", "approver")
    [pending] = (await platform.http.get("/console/approvals", headers=lead)).json()["approvals"]
    assert pending["ticket_id"] == ticket["id"] and pending["args"]["amount_cents"] == 18000
    # The requester cannot approve their own refund, even with the approver role.
    selfish = platform.user("c-ana", "customer", "approver")
    url = f"/console/approvals/{pending['id']}/decision"
    assert (await platform.http.post(url, json={"decision": "approve"}, headers=selfish)).status_code == 403

    ok = await platform.http.post(url, json={"decision": "approve", "note": "photo checked"}, headers=lead)
    assert ok.status_code == 200 and ok.json()["approval"]["status"] == "approved"
    assert platform.store.orders["O-1002"]["refunded_cents"] == 18000
    again = await platform.http.post(url, json={"decision": "approve"}, headers=lead)
    assert again.status_code == 409 and platform.store.orders["O-1002"]["refunded_cents"] == 18000  # once only

    done = (await platform.http.get(f"/v1/tickets/{ticket['id']}", headers=ana)).json()
    assert done["status"] == "resolved" and "Refunded 180.00 EUR" in done["messages"][-1]["text"]
    log = [(d["tool"], d["decision"]) for d in await platform.decisions(tenant="customer")]
    assert ("orders__refund", "hold") in log and ("orders__refund", "approved") in log
    row = (await platform.admin["checkpoint"].get("/approvals?status=used", headers=lead)).status_code
    assert row == 401  # the console's people never hold Checkpoint credentials


async def test_cross_tenant_attempts_fail_closed(platform):
    """A fully compromised billing agent, acting for a customer, reaches for the employee desk's systems and data."""
    platform.script(
        cust_triage=[calls(("handoff", {"to": "billing", "summary": "x"}))],
        billing=[
            calls(
                ("idp__unlock_account", {"user_id": "e-cy"}),
                ("orders__get_order", {"order_id": "O-2001"}),  # another customer's order
                ("ticketing__get_ticket", {"ticket_id": "T-employee"}),
            ),
            "done",
        ],
    )
    platform.store.tickets[("employee", "T-employee")] = {"notes": [{"by": "it", "note": "secret"}], "resolution": None}
    ticket = await platform.open(platform.user(*ANA), "show me everything")
    trace = await platform.trace(ticket["id"], platform.user("c-sup", "customer", "supervisor"))
    results = {e["detail"]["tool"]: e["detail"] for e in trace["events"] if e["kind"] == "tool_call"}
    assert "idp__unlock_account" not in results  # never listed for billing, so never sent anywhere
    refusal = next(m for m in trace["messages"] if m["role"] == "tool" and "no tool called idp__unlock" in m["content"])
    assert refusal["agent_id"] == "billing"
    assert results["orders__get_order"]["result"] == "order not found"
    assert results["ticketing__get_ticket"]["outcome"] in ("error", "denied")
    assert "secret" not in str(trace) and platform.store.accounts["e-cy"]["locked"] is True

    # And a customer's token handed to an employee-desk agent is refused by Checkpoint before policy runs.
    creds = platform.hd_cfg.agents["it-access"]
    hd = platform.hd.state.checkpoint
    anonymous = {t["name"] for t in await hd.list_tools(creds.checkpoint_token, None)}
    assert not any(n.startswith("idp__") for n in anonymous)  # no signed-in employee: the IdP wall stays shut
    unlock = {"name": "idp__unlock_account", "inputSchema": {}}
    stolen = platform.user(*ANA)["authorization"].removeprefix("Bearer ")
    r = await hd.call(creds.checkpoint_token, stolen, unlock, {"user_id": "c-ana"})
    assert r.outcome == "refused" and "different tenant" in r.text


async def test_rows_are_isolated_by_row_level_security(platform):
    platform.script(cust_triage=["Hello! What can I help with?"], emp_triage=["Hi, what do you need?"])
    mine = await platform.open(platform.user(*ANA), "hello")
    await platform.open(platform.user(*ADA), "hello")
    # The same user id in the other tenant sees nothing, and a forgotten tenant filter returns no rows at all.
    imposter = platform.user("c-ana", "employee")
    assert (await platform.http.get(f"/v1/tickets/{mine['id']}", headers=imposter)).status_code == 404
    async with platform.hd.state.pool.connection() as c:
        assert (await (await c.execute("SELECT count(*) AS n FROM tickets")).fetchone())["n"] == 0


async def test_handoff_loops_and_unknown_targets_go_to_a_person(platform):
    platform.script(cust_triage=[calls(("handoff", {"to": "it-access", "summary": "wrong desk"}))])
    ticket = await platform.open(platform.user(*ANA), "my VPN is broken")
    assert ticket["status"] == "escalated"
    sup = platform.user("c-sup", "customer", "supervisor")
    [esc] = (await platform.http.get("/console/escalations", headers=sup)).json()["escalations"]
    assert "not allowed" in esc["reason"] and esc["ticket_id"] == ticket["id"]
    r = await platform.http.post(
        f"/console/escalations/{esc['id']}/resolve", json={"reply": "We do not run VPNs."}, headers=sup
    )
    assert r.status_code == 200
    view = (await platform.http.get(f"/v1/tickets/{ticket['id']}", headers=platform.user(*ANA))).json()
    assert view["status"] == "resolved" and view["messages"][-1]["text"] == "We do not run VPNs."


async def test_kill_switch_hands_tickets_to_people(platform):
    sup = platform.user("e-sup", "employee", "supervisor")
    r = await platform.http.put(
        "/console/agents/emp-triage/switch", json={"enabled": False, "reason": "drill"}, headers=sup
    )
    assert r.status_code == 200
    other = await platform.http.put(
        "/console/agents/billing/switch", json={"enabled": False, "reason": "x"}, headers=sup
    )
    assert other.status_code == 404  # another tenant's agent
    ticket = await platform.open(platform.user(*ADA), "help")
    assert ticket["status"] == "escalated" and provider.state["requests"] == []  # no model call at all


async def test_a_spent_budget_degrades_to_a_person(platform):
    await platform.admin["switchboard"].put(
        "/admin/apps/cust-triage-evals/policy", json={"allowed_models": ["helpdesk-small"], "budget_usd_month": 0}
    )
    ticket = await platform.open(platform.user(*ANA), "where is my order?")
    assert ticket["status"] == "escalated"
    sup = platform.user("c-sup", "customer", "supervisor")
    [esc] = (await platform.http.get("/console/escalations", headers=sup)).json()["escalations"]
    assert esc["reason"] == "model budget exhausted"


async def test_cost_per_resolved_ticket_joins_the_ledger_to_outcomes(platform):
    await test_account_unlock_end_to_end(platform)
    await platform.settle()
    month = (await platform.admin["switchboard"].get("/admin/usage", params={"month": "2026-01"})).status_code
    assert month == 200
    from datetime import date

    report = (
        await platform.admin["helpdesk"].get("/admin/finops", params={"month": date.today().strftime("%Y-%m")})
    ).json()
    employee = next(t for t in report["tenants"] if t["tenant"] == "employee")
    # 5 calls of 1000 input and 100 output tokens at 2 and 8 USD per million: 5 * 0.0028 = 0.014 USD
    assert employee["resolved"] == 1 and abs(employee["model_cost_usd"] - 0.014) < 1e-9
    assert employee["cost_per_resolved_usd"] == round(0.014, 4)
    it = next(a for a in report["agents"] if a["agent"] == "it-access")
    assert it["resolved"] == 1 and it["requests"] == 4


async def test_evidence_pack_and_disclosure(platform):
    for path, tenant in (("/", "customer"), ("/staff", "employee")):
        html = (await platform.http.get(path)).text
        assert 'data-testid="ai-disclosure"' in html and "You are chatting with an AI assistant" in html, tenant
    await platform.admin["helpdesk"].post("/admin/purge")
    pack = (await platform.admin["helpdesk"].get("/admin/evidence")).json()
    kinds = {(a["kind"], a["status"]) for a in pack["inventory"]["atlas"]}
    assert kinds == {("mcp_server", "approved"), ("a2a_agent", "approved"), ("skill", "approved")}
    assert len(pack["inventory"]["atlas"]) == 4 + 6 + 6
    hr = next(a for a in pack["inventory"]["agents"] if a["id"] == "hr-policy")
    assert "Annex III point 4" in hr["risk"]["note"] and hr["skill_digest"].startswith("sha256:")
    assert pack["retention"]["recent_purges"] and set(pack["disclosure"]) == {"customer", "employee"}
