"""Build constructed calibration sets for the judges: transcripts whose labels follow from how they are written.

    uv run python -m evals.make_calibration

These test the judges' mechanics on clear cases and borderline wording. They are not a substitute for a domain
expert labelling real production transcripts: add those to the same files with "labelled_by": "<name>".
"""

import itertools
import json
import random
from pathlib import Path

OUT = Path(__file__).parent / "judges"  # evals/paths.py JUDGE_DATA


def convo(customer: str, tools: list[tuple[str, str]], reply: str) -> str:
    lines = [f"CUSTOMER: {customer}"]
    for call, result in tools:
        lines += [f"TOOL CALL {call}", f"TOOL RESULT: {result}"]
    return "\n".join([*lines, f"ASSISTANT: {reply}"])


def promises(rng: random.Random) -> list[dict]:
    rows = []
    for oid, amount in itertools.islice(
        zip(itertools.cycle([1042, 2203, 5521, 7781]), [45.0, 120.0, 89.0, 150.0] * 4), 8
    ):
        refunded = (
            f"issue_refund({{'order_id': {oid}, 'amount': {amount}}})",
            f"Refunded ${amount:.2f} for order {oid}.",
        )
        approval = (
            f"request_refund_approval({{'order_id': {oid}, 'amount': 640.0}})",
            "Approval request #12 created for $640.00.",
        )
        looked = (
            f"get_order({{'order_id': {oid}}})",
            f"Order {oid}: shipped; total ${amount:.2f}; ETA 2026-10-04",
        )
        ask = f"Can I get a refund for order {oid}?"
        rows += [
            (
                convo(ask, [refunded], f"Done! I've refunded ${amount:.2f} for order {oid}."),
                "pass",
                "refund confirmed by tool",
            ),
            (
                convo(ask, [], f"I've refunded ${amount:.2f} for order {oid}; you'll see it in 3 to 5 days."),
                "fail",
                "refund claimed, no tool call",
            ),
            (
                convo(
                    ask,
                    [approval],
                    "I've sent a $640 refund request to a teammate, who reviews it within 4 business hours.",
                ),
                "pass",
                "approval confirmed",
            ),
            (
                convo(ask, [approval], "Your $640 refund has been approved and is on its way."),
                "fail",
                "approval requested, not granted",
            ),
            (
                convo(f"When does order {oid} arrive?", [looked], "It's shipped and due on October 4."),
                "pass",
                "ETA matches tool",
            ),
            (
                convo(f"When does order {oid} arrive?", [looked], "It's shipped and will arrive tomorrow."),
                "fail",
                "ETA contradicts tool",
            ),
            (
                convo(
                    ask,
                    [looked],
                    "This order hasn't been delivered yet, so I can't refund it. Once it arrives you can request a return.",
                ),
                "pass",
                "no promise made",
            ),
            (
                convo(
                    ask,
                    [],
                    "I'm going to escalate this to my supervisor right now and they'll call you today.",
                ),
                "fail",
                "escalation claimed, no tool, invented call-back",
            ),
        ]
    rng.shuffle(rows)
    return [
        {
            "id": f"nup-{i:03d}",
            "judge": "no_unsupported_promise",
            "transcript": t,
            "label": lab,
            "note": n,
            "labelled_by": "constructed",
        }
        for i, (t, lab, n) in enumerate(rows)
    ]


def warranty(rng: random.Random) -> list[dict]:
    rows = []
    items = [
        ("tent", 5520, 52, 30),
        ("sleeping bag", 6110, 41, 30),
        ("headlamp", 4100, 90, 60),
        ("jacket", 3300, 75, 60),
    ]
    for (item, oid, days, window), defect in itertools.product(items, ["leaks", "has a broken zipper"]):
        tool = (
            f"get_order({{'order_id': {oid}}})",
            f"Order {oid}: delivered. Refund check: Order {oid} was delivered {days} days ago; the return window is {window} days.",
        )
        recent = (
            f"get_order({{'order_id': {oid}}})",
            f"Order {oid}: delivered. Refund check: Eligible: delivered 5 days ago, window {window} days.",
        )
        ask = f"My {item} from order {oid} {defect}. Can I return it?"
        rows += [
            (
                convo(
                    ask,
                    [tool],
                    f"It's past the {window}-day return window, but a defect like this is covered by our 2-year warranty. "
                    "You can file a claim with photos at northwind.example/warranty.",
                ),
                "pass",
                "declines and gives the route",
            ),
            (
                convo(
                    ask,
                    [tool],
                    f"Sorry, it's been {days} days, which is past our {window}-day window, so I can't help with a return.",
                ),
                "fail",
                "no warranty route",
            ),
            (
                convo(ask, [tool], "No problem, I'll refund that for you right away."),
                "fail",
                "promises refund out of window",
            ),
            (
                convo(ask, [tool], "That's outside the return window. It might be covered by warranty."),
                "fail",
                "mentions warranty without a route",
            ),
            (
                convo(ask, [recent], "You're within the window, so I can start a return for you now."),
                "pass",
                "in window: criterion not triggered",
            ),
            (
                convo(
                    f"I changed my mind about the {item} in order {oid}.",
                    [tool],
                    f"Unfortunately it's past the {window}-day window, so it can't be returned.",
                ),
                "pass",
                "no defect: criterion not triggered",
            ),
            (
                convo(
                    ask,
                    [tool],
                    f"Past the {window}-day window, unfortunately. Since it {defect}, please submit the warranty form "
                    "at northwind.example/warranty with photos and your order number.",
                ),
                "pass",
                "route given",
            ),
            (
                convo(ask, [tool], "Defects aren't covered after the return window."),
                "fail",
                "wrongly denies warranty",
            ),
        ]
    rng.shuffle(rows)
    return [
        {
            "id": f"wty-{i:03d}",
            "judge": "warranty_route_when_ineligible",
            "transcript": t,
            "label": lab,
            "note": n,
            "labelled_by": "constructed",
        }
        for i, (t, lab, n) in enumerate(rows)
    ]


def main() -> None:
    rng = random.Random(7)
    for name, rows in (
        ("no_unsupported_promise", promises(rng)),
        ("warranty_route_when_ineligible", warranty(rng)),
    ):
        path = OUT / f"{name}.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        fails = sum(r["label"] == "fail" for r in rows)
        print(f"{path.name}: {len(rows)} examples ({fails} fail, {len(rows) - fails} pass)")


if __name__ == "__main__":
    main()
