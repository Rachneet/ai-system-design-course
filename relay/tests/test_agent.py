import asyncio

from app import agent
from app.tools import REGISTRY, Tool
from tests.fakes import ScriptedLLM, text, tool_use

USER = {"role": "user", "content": [{"type": "text", "text": "hi"}]}


async def collect(ctx, llm):
    chunks = []

    async def on_text(t):
        chunks.append(t)

    result = await agent.run_turn(ctx, llm, "system", [USER], on_text)
    return result, "".join(chunks)


async def test_tool_then_answer(ctx):
    llm = ScriptedLLM(tool_use(("get_order", {"order_id": 1042})), text("It was delivered."))
    result, streamed = await collect(ctx, llm)
    assert [m["role"] for m in result.new_messages] == ["assistant", "user", "assistant"]
    assert result.tool_calls == [{"name": "get_order", "input": {"order_id": 1042}, "is_error": False}]
    assert streamed == "It was delivered." and result.stopped is None
    assert llm.requests[1]["messages"][-1]["content"][0]["type"] == "tool_result"


async def test_parallel_calls_return_in_one_message(ctx):
    llm = ScriptedLLM(tool_use(("get_order", {"order_id": 1042}), ("list_orders", {})), text("done"))
    result, _ = await collect(ctx, llm)
    results = result.new_messages[1]["content"]
    assert len(results) == 2 and all(r["type"] == "tool_result" for r in results)


async def test_tool_errors_are_returned_to_the_model(ctx):
    llm = ScriptedLLM(tool_use(("get_order", {"order_id": 2210}), ("no_such_tool", {})), text("ok"))
    result, _ = await collect(ctx, llm)
    assert [c["is_error"] for c in result.tool_calls] == [True, True]


async def test_step_limit_escalates(ctx, store, monkeypatch):
    monkeypatch.setattr(agent.settings, "max_steps", 3)
    llm = ScriptedLLM(*[tool_use(("list_orders", {})) for _ in range(3)])
    result, streamed = await collect(ctx, llm)
    assert result.stopped == "step_limit" and agent.STEP_LIMIT_REPLY in streamed
    assert result.new_messages[-1]["role"] == "assistant"


async def test_truncated_tool_call_is_not_executed(ctx, store):
    llm = ScriptedLLM(
        tool_use(
            ("issue_refund", {"order_id": 1042, "amount": 45.0, "reason": "x"}), stop_reason="max_tokens"
        )
    )
    result, _ = await collect(ctx, llm)
    assert result.stopped == "max_tokens" and await store.refund_for(1042) is None
    closing = result.new_messages[-1]["content"][0]
    assert closing["type"] == "tool_result" and closing["is_error"]  # history stays valid for the next turn


async def test_slow_tool_times_out(ctx, monkeypatch):
    async def slow(ctx):
        await asyncio.sleep(1)
        return "late"

    monkeypatch.setitem(
        REGISTRY, "slow", Tool("slow", "slow", {"type": "object", "properties": {}}, slow, "read")
    )
    monkeypatch.setattr(agent.settings, "tool_timeout_s", 0.05)
    llm = ScriptedLLM(tool_use(("slow", {})), text("sorry"))
    result, _ = await collect(ctx, llm)
    assert result.tool_calls[0]["is_error"]
