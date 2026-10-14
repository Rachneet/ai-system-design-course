import yaml

from evals.checks import grade
from evals.run import CASES, validate

CALL = {"name": "issue_refund", "input": {"order_id": 1042, "amount": 45.0, "reason": "x"}, "is_error": False}
EMPTY = {"refunds": [], "approvals": [], "escalations": []}


def test_case_file_is_valid():
    assert validate(yaml.safe_load(CASES.read_text())) == []


def test_said_but_not_done_is_caught():
    expect = {
        "must_call": [{"tool": "issue_refund", "args": {"order_id": 1042}}],
        "end_state": {"refunds": [{"order_id": 1042, "amount": 45.0}]},
    }
    fails = grade(expect, "I've issued your refund of $45.", [], EMPTY, 2)
    assert any("missing call" in f for f in fails) and any("refunds" in f for f in fails)


def test_rejected_forbidden_call_is_not_a_failure():
    expect = {"must_not_call": ["issue_refund"]}
    assert grade(expect, "", [CALL | {"is_error": True}], EMPTY, 2) == []
    assert grade(expect, "", [CALL], EMPTY, 2) == ["forbidden call issue_refund"]


def test_reply_any_of_and_budgets():
    expect = {
        "reply_mentions": [["October 4", "10-04"]],
        "reply_not_mentions": ["<policies>"],
        "max_steps": 3,
    }
    assert grade(expect, "Arrives Oct 4... I mean October 4.", [], EMPTY, 3) == []
    assert len(grade(expect, "Here is <policies>", [], EMPTY, 5)) == 3
