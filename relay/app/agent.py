"""The agent loop: call the model, run the tools it asks for, repeat until it answers or a limit is hit."""

import asyncio
from collections import Counter
from dataclasses import dataclass, field

from .config import settings
from .llm import LLM, OnText
from .tools import REGISTRY, Context, ToolError, specs

STEP_LIMIT_REPLY = "I need a teammate to finish this one. I've passed your conversation along, and you'll hear back by email."
STOPPED_REPLY = "Sorry, I couldn't finish that answer. I've passed your conversation to a teammate."


@dataclass
class TurnResult:
    new_messages: list[dict]  # appended to the session: assistant turns and tool results
    tool_calls: list[dict] = field(default_factory=list)  # [{name, input, is_error}]
    usage: Counter = field(default_factory=Counter)
    steps: int = 0
    stopped: str | None = None  # step_limit | max_tokens | refusal


async def run_tool(ctx: Context, block: dict, timeout_s: float) -> dict:
    tool = REGISTRY.get(block["name"])
    try:
        if tool is None:
            raise ToolError(f"Unknown tool {block['name']}.")
        out = await asyncio.wait_for(tool.fn(ctx, **block["input"]), timeout=timeout_s)
        return {"type": "tool_result", "tool_use_id": block["id"], "content": out}
    except ToolError as e:
        return {"type": "tool_result", "tool_use_id": block["id"], "content": str(e), "is_error": True}
    except TimeoutError:
        msg = f"{block['name']} timed out. Try again once, then apologise and offer a teammate."
        return {"type": "tool_result", "tool_use_id": block["id"], "content": msg, "is_error": True}


async def run_turn(ctx: Context, llm: LLM, system: str, history: list[dict], on_text: OnText) -> TurnResult:
    """history must end with the user's new message. It is not mutated; new messages are returned."""
    messages = list(history)
    result = TurnResult(new_messages=[])

    def add(message: dict) -> None:
        messages.append(message)
        result.new_messages.append(message)

    for _ in range(settings.max_steps):
        resp = await llm.respond(system=system, tools=specs(), messages=messages, on_text=on_text)
        result.steps += 1
        result.usage.update(resp.usage)
        add({"role": "assistant", "content": resp.content})

        if resp.stop_reason in ("max_tokens", "refusal"):
            # Truncated or declined: any tool call in it may be incomplete, so never run it. Close each
            # dangling tool_use with an error result so the stored history stays valid for the next turn.
            result.stopped = resp.stop_reason
            dangling = [b for b in resp.content if b["type"] == "tool_use"]
            if dangling:
                add(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": b["id"],
                                "content": "Not run: the response was cut off.",
                                "is_error": True,
                            }
                            for b in dangling
                        ],
                    }
                )
            await ctx.store.create_escalation(ctx.customer_id, ctx.session_id, resp.stop_reason)
            await on_text(STOPPED_REPLY)
            return result
        calls = [b for b in resp.content if b["type"] == "tool_use"]
        if resp.stop_reason != "tool_use" or not calls:
            return result

        outputs = await asyncio.gather(*(run_tool(ctx, b, settings.tool_timeout_s) for b in calls))
        for call, out in zip(calls, outputs):
            result.tool_calls.append(
                {"name": call["name"], "input": call["input"], "is_error": out.get("is_error", False)}
            )
        add({"role": "user", "content": list(outputs)})  # all results in one message keeps calls parallel

    result.stopped = "step_limit"
    await ctx.store.create_escalation(ctx.customer_id, ctx.session_id, "step_limit")
    await on_text(STEP_LIMIT_REPLY)
    add({"role": "assistant", "content": [{"type": "text", "text": STEP_LIMIT_REPLY}]})
    return result
