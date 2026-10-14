from app import agent
from app.guardrails import check_reply, redact_cards
from tests.fakes import ScriptedLLM, text, tool_use

APPROVAL = {"name": "request_refund_approval", "input": {}, "is_error": False}


def test_card_numbers_are_redacted_but_order_numbers_are_not():
    out, n = redact_cards("card 4111 1111 1111 1111, order 1042, ref 1234567812345678")
    assert n == 1 and "[CARD REDACTED]" in out and "1042" in out and "1234567812345678" in out


def test_citations_must_come_from_this_turns_search():
    assert check_reply("Within 30 days [POL-RETURNS-2026].", {"POL-RETURNS-2026"}, []) == []
    assert check_reply("Within 90 days [POL-RETURNS-2019].", {"POL-RETURNS-2026"}, [])


def test_refund_promises_above_the_limit():
    assert check_reply("I've refunded $640 to your card.", set(), [])
    assert check_reply("I've refunded $640 to your card.", set(), [APPROVAL]) == []
    assert check_reply("Your order total was $640 and it is eligible for a refund.", set(), []) == []
    assert check_reply("I've refunded $45.00.", set(), []) == []


async def test_failed_draft_is_rewritten_and_never_shown(ctx):
    llm = ScriptedLLM(text("You have 90 days [POL-FAKE-1]."), text("You have 30 days for used tents."))
    shown = []

    async def on_text(t):
        shown.append(t)

    guard = lambda draft, result: check_reply(draft, ctx.retrieved, result.tool_calls)
    user = {"role": "user", "content": [{"type": "text", "text": "return window?"}]}
    result = await agent.run_turn(ctx, llm, "s", [user], on_text, guard=guard)
    assert shown == ["You have 30 days for used tents."] and result.guard_failures
    assert llm.requests[1]["messages"][-1]["content"][0]["text"].startswith("<guardrail>")


async def test_second_failure_falls_back_and_escalates(ctx, store):
    llm = ScriptedLLM(text("I've refunded $640."), text("Done, I've refunded $640 for you."))
    shown = []

    async def on_text(t):
        shown.append(t)

    user = {"role": "user", "content": [{"type": "text", "text": "refund 3001"}]}
    result = await agent.run_turn(
        ctx, llm, "s", [user], on_text, guard=lambda d, r: check_reply(d, set(), r.tool_calls)
    )
    assert shown == [agent.GUARD_FALLBACK] and result.stopped == "guardrail"
    assert [m["role"] for m in result.new_messages] == ["assistant", "user", "assistant", "user", "assistant"]


async def test_interim_text_with_tool_calls_is_shown_when_clean(ctx):
    first = tool_use(("get_order", {"order_id": 1042}))
    first.content.insert(0, {"type": "text", "text": "Let me check. "})
    shown = []

    async def on_text(t):
        shown.append(t)

    user = {"role": "user", "content": [{"type": "text", "text": "order?"}]}
    await agent.run_turn(
        ctx,
        ScriptedLLM(first, text("Delivered.")),
        "s",
        [user],
        on_text,
        guard=lambda d, r: check_reply(d, ctx.retrieved, r.tool_calls),
    )
    assert shown == ["Let me check. ", "Delivered."]
