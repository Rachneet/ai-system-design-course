"""helpdesk.cedar, evaluated by Checkpoint's own policy engine. Least privilege is proven here, not in prompts."""

from pathlib import Path

import pytest
from checkpoint.policy import Policy

from helpdesk.servers.systems import Store, all_servers

POLICY = Policy((Path(__file__).parents[1] / "policies" / "helpdesk.cedar").read_text())
SERVERS = all_servers(Store())
TOOLS = {f"{slug}__{t.name}": (s.name, t) for slug, s in SERVERS.items() for t in s.tools.values()}
WRITES = sorted(name for name, (_, t) in TOOLS.items() if not t.read_only)
EMPLOYEE = {"id": "e-ada", "roles": ["staff"], "tenant": "employee"}
CUSTOMER = {"id": "c-ana", "roles": ["customer"], "tenant": "customer"}


def decide(agent, tool, args=None, user=EMPLOYEE, action="call"):
    tenant = user["tenant"]
    ctx = {"args": args or {}, "user": user, "agent": {"tenant": tenant}, "server": TOOLS[tool][0]}
    return POLICY.decide(agent, action, tool, ctx)


def test_the_catalog_has_the_writes_this_file_reasons_about():
    assert WRITES == [
        "idp__request_group_access",
        "idp__unlock_account",
        "orders__create_return",
        "orders__refund",
        "ticketing__add_note",
        "ticketing__resolve_ticket",
    ]


@pytest.mark.parametrize("tool", WRITES)
@pytest.mark.parametrize("user", [EMPLOYEE, CUSTOMER])
def test_the_hr_agent_reaches_no_write_tool_whatever_the_arguments(tool, user):
    for args in ({}, {"user_id": user["id"], "group": "vpn-users", "amount_cents": 1}, {"ticket_id": "T-1"}):
        assert not decide("hr-policy", tool, args, user).allowed
        assert not decide("hr-policy", tool, args, user, action="list").allowed


@pytest.mark.parametrize("triage", ["emp-triage", "cust-triage"])
def test_triage_agents_have_no_tools(triage):
    for tool in TOOLS:
        assert not decide(triage, tool, {"user_id": "e-ada"}).allowed


def test_it_access_unlocks_only_the_callers_own_account():
    assert decide("it-access", "idp__unlock_account", {"user_id": "e-ada"}).allowed
    other = decide("it-access", "idp__unlock_account", {"user_id": "e-bo"})
    assert not other.allowed and other.policies == []
    assert not decide("it-access", "idp__unlock_account", {}).allowed


def test_sensitive_groups_need_a_person_and_unknown_groups_are_refused():
    std = decide("it-access", "idp__request_group_access", {"user_id": "e-ada", "group": "vpn-users"})
    assert std.allowed and not std.needs_approval
    hot = decide("it-access", "idp__request_group_access", {"user_id": "e-ada", "group": "prod-admins"})
    assert hot.allowed and hot.needs_approval and hot.policies == ["it-sensitive-groups-need-approval"]
    assert not decide("it-access", "idp__request_group_access", {"user_id": "e-ada", "group": "root"}).allowed
    assert not decide("it-access", "idp__request_group_access", {"user_id": "e-bo", "group": "vpn-users"}).allowed


@pytest.mark.parametrize(
    ("cents", "allowed", "approval", "policy"),
    [
        (4900, True, False, "refunds-up-to-50"),
        (5000, True, False, "refunds-up-to-50"),
        (5001, True, True, "refunds-up-to-500-need-approval"),
        (50000, True, True, "refunds-up-to-500-need-approval"),
        (50001, False, False, "refunds-above-500-are-for-people"),
    ],
)
def test_refund_bands(cents, allowed, approval, policy):
    d = decide("billing", "orders__refund", {"order_id": "O-1", "amount_cents": cents}, CUSTOMER)
    assert (d.allowed, d.needs_approval, d.policies) == (allowed, approval, [policy])


def test_specialists_stay_in_their_lane():
    assert not decide("returns", "orders__refund", {"amount_cents": 100}, CUSTOMER).allowed
    assert not decide("returns", "orders__refund", user=CUSTOMER, action="list").allowed
    assert not decide("billing", "orders__create_return", {"order_id": "O-1"}, CUSTOMER).allowed
    assert not decide("billing", "idp__unlock_account", {"user_id": "c-ana"}, CUSTOMER).allowed
    assert decide("returns", "orders__create_return", {"order_id": "O-1", "reason": "x"}, CUSTOMER).allowed


def test_tenant_walls_hold_even_for_a_misbound_agent():
    """If an agent were registered without its tenant, the forbids still keep each tenant's systems apart."""
    wall = decide("it-access", "idp__unlock_account", {"user_id": "c-ana"}, CUSTOMER)
    assert not wall.allowed and wall.policies == ["idp-is-employee-only"]
    wall = decide("billing", "orders__list_orders", {}, EMPLOYEE)
    assert not wall.allowed and wall.policies == ["orders-is-customer-only"]


def test_no_decision_hits_an_evaluation_error():
    for agent in ("it-access", "hr-policy", "billing", "returns", "emp-triage"):
        for tool in TOOLS:
            for user in (EMPLOYEE, CUSTOMER):
                assert not decide(agent, tool, {}, user).errors, (agent, tool)
