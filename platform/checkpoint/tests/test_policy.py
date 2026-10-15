"""Policy evaluation without a database: how Cedar's evaluation errors become decisions."""

from checkpoint.policy import Policy

GUARDED = """
@id("allow-refunds")
permit(principal == Agent::"refunds", action == Action::"call", resource == Tool::"payments__refund");

@id("cap-refunds")
forbid(principal, action == Action::"call", resource == Tool::"payments__refund")
when { context.args.amount > 2000 };

@id("vip-only")
permit(principal == Agent::"concierge", action == Action::"call", resource == Tool::"payments__refund")
when { context.user.tier == "vip" };
"""


def decide(agent, args, user=None):
    ctx = {"args": args, "user": user or {"id": "u1", "roles": []}, "server": "com.acme/payments"}
    return Policy(GUARDED).decide(agent, "call", "payments__refund", ctx)


def test_a_forbid_that_cannot_evaluate_fails_closed():
    d = decide("refunds", {"customer_id": "c1"})  # no amount: the cap cannot be checked
    assert not d.allowed and d.policies == ["cap-refunds"]
    assert d.errors and "cap-refunds" in d.errors[0] and "amount" in d.errors[0]


def test_a_permit_that_cannot_evaluate_simply_does_not_permit():
    d = decide("concierge", {"amount": 5})  # the user has no tier attribute
    assert not d.allowed and d.policies == [] and "vip-only" in d.errors[0]


def test_well_formed_requests_decide_without_errors():
    assert decide("refunds", {"amount": 5}).allowed and not decide("refunds", {"amount": 5}).errors
    big = decide("refunds", {"amount": 5000})
    assert not big.allowed and big.policies == ["cap-refunds"] and not big.errors
