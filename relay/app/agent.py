"""The agent loop: call the model, run the tools it asks for, repeat until it answers or a limit is hit."""

import asyncio
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from .config import settings
from .llm import LLM, OnText
from .tools import REGISTRY, Context, ToolError, specs

STEP_LIMIT_REPLY = "I need a teammate to finish this one. I've passed your conversation along, and you'll hear back by email."
STOPPED_REPLY = "Sorry, I couldn't finish that answer. I've passed your conversation to a teammate."
GUARD_FALLBACK = (
    "Sorry, I couldn't put together a reliable answer to that. I've passed your conversation to a teammate."
)

# A guard returns a list of problems with a draft reply; empty means it may be shown.
Guard = Callable[[str, "TurnResult"], list[str]]


@dataclass
class TurnResult:
    new_messages: list[dict]  # appended to the session: assistant turns, tool results, guardrail notes
    tool_calls: list[dict] = field(default_factory=list)  # [{name, input, is_error}]
    usage: Counter = field(default_factory=Counter)
    steps: int = 0
    stopped: str | None = None  # step_limit | max_tokens | refusal | guardrail
    guard_failures: list[str] = field(default_factory=list)


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


def _text(content: list[dict]) -> str:
    return "".join(b["text"] for b in content if b["type"] == "text")


async def run_turn(
    ctx: Context,
    llm: LLM,
    system: str,
    history: list[dict],
    on_text: OnText,
    guard: Guard | None = None,
    rewrites: int = 1,
) -> TurnResult:
    """history must end with the user's new message. It is not mutated; new messages are returned.

    With a guard, text is held back until the step finishes and the guard passes. That costs time to first
    token on the final answer, which is acceptable for short support replies and is the safe choice when a
    failure would leak data or promise money.
    """
    messages = list(history)
    result = TurnResult(new_messages=[])

    def add(message: dict) -> None:
        messages.append(message)
        result.new_messages.append(message)

    async def hold(_: str) -> None:
        return None

    for _ in range(settings.max_steps):
        resp = await llm.respond(
            system=system, tools=specs(), messages=messages, on_text=hold if guard else on_text
        )
        result.steps += 1
        result.usage.update(resp.usage)
        add({"role": "assistant", "content": resp.content})
        draft = _text(resp.content)

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
        if resp.stop_reason == "tool_use" and calls:
            if guard and draft and not guard(draft, result):
                await on_text(draft)  # interim text ("Let me check that order") is shown only if it passes
            outputs = await asyncio.gather(*(run_tool(ctx, b, settings.tool_timeout_s) for b in calls))
            for call, out in zip(calls, outputs, strict=True):
                result.tool_calls.append(
                    {"name": call["name"], "input": call["input"], "is_error": out.get("is_error", False)}
                )
            add({"role": "user", "content": list(outputs)})  # all results in one message keeps calls parallel
            continue

        problems = guard(draft, result) if guard else []
        if not problems:
            if guard:
                await on_text(draft)
            return result
        result.guard_failures += problems
        note = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "<guardrail>Your previous draft was not sent to the customer because it "
                        + "; ".join(problems)
                        + ". Write the reply again, fixing this. Only cite documents returned by "
                        "search_kb in this conversation, and only describe refunds that a tool result confirms.</guardrail>"
                    ),
                }
            ],
        }
        add(note)
        if rewrites > 0:
            rewrites -= 1
            continue
        result.stopped = "guardrail"
        await ctx.store.create_escalation(ctx.customer_id, ctx.session_id, "guardrail")
        add({"role": "assistant", "content": [{"type": "text", "text": GUARD_FALLBACK}]})
        await on_text(GUARD_FALLBACK)
        return result

    result.stopped = "step_limit"
    await ctx.store.create_escalation(ctx.customer_id, ctx.session_id, "step_limit")
    await on_text(STEP_LIMIT_REPLY)
    add({"role": "assistant", "content": [{"type": "text", "text": STEP_LIMIT_REPLY}]})
    return result
