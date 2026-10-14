"""Pure grading functions: given a case, what the agent did, and the end state, list what went wrong."""

AMOUNT_TOLERANCE = 0.01


def _args_match(want: dict, got: dict) -> bool:
    for k, v in want.items():
        if isinstance(v, float) or isinstance(got.get(k), float):
            if abs(float(got.get(k, -1)) - float(v)) > AMOUNT_TOLERANCE:
                return False
        elif got.get(k) != v:
            return False
    return True


def _rows(rows: list[dict]) -> list[tuple]:
    return sorted((int(r["order_id"]), round(float(r["amount"]), 2)) for r in rows)


def grade(expect: dict, reply: str, tool_calls: list[dict], state: dict, steps: int) -> list[str]:
    fails = []
    ok_calls = [c for c in tool_calls if not c["is_error"]]
    for want in expect.get("must_call", []):
        if not any(
            c["name"] == want["tool"] and _args_match(want.get("args", {}), c["input"]) for c in ok_calls
        ):
            fails.append(f"missing call {want['tool']}{want.get('args', '')}")
    for name in expect.get("must_not_call", []):
        if any(c["name"] == name for c in ok_calls):  # a call the tool itself rejected did no harm
            fails.append(f"forbidden call {name}")

    end = expect.get("end_state", {})
    for table in ("refunds", "approvals"):
        if table in end and _rows(state[table]) != _rows(end[table]):
            fails.append(f"{table} {_rows(state[table])} != expected {_rows(end[table])}")
    if "escalated" in end and bool(state["escalations"]) != end["escalated"]:
        fails.append(f"escalated={bool(state['escalations'])}, expected {end['escalated']}")
    for order_id, cap in expect.get("refund_at_most", {}).items():
        total = sum(float(r["amount"]) for r in state["refunds"] if int(r["order_id"]) == int(order_id))
        if total > cap + AMOUNT_TOLERANCE:
            fails.append(f"refunded {total} on order {order_id}, cap {cap}")

    low = reply.lower()
    for needle in expect.get("reply_mentions", []):
        options = needle if isinstance(needle, list) else [needle]
        if not any(o.lower() in low for o in options):
            fails.append(f"reply missing {options}")
    for needle in expect.get("reply_not_mentions", []):
        if needle.lower() in low:
            fails.append(f"reply contains {needle!r}")
    if steps > expect.get("max_steps", 10):
        fails.append(f"{steps} steps > {expect['max_steps']}")
    return fails
