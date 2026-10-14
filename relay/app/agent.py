"""The agent loop: call the model, run the tools it asks for, repeat until it answers or a limit is hit."""

import asyncio
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from opentelemetry.trace import Status, StatusCode

from . import metrics
from .config import settings
from .llm import LLM, LLMResponse, OnText
from .pricing import cost_usd
from .telemetry import record_content, tracer
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
    cost_usd: float = 0.0  # priced per call by the model that actually served it (fallbacks are cheaper)


async def run_tool(ctx: Context, block: dict, timeout_s: float) -> dict:
    name = block["name"]
    tool = REGISTRY.get(name)
    with tracer.start_as_current_span(f"execute_tool {name}") as span:
        span.set_attributes(
            {
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": name,
                "gen_ai.tool.call.id": block["id"],
                "relay.tool.tier": tool.tier if tool else "unknown",
            }
        )
        try:
            if tool is None or tool.tier not in ctx.allowed_tiers or name in ctx.disabled_tools:
                raise ToolError(f"Tool {name} is not available here.")
            out = await asyncio.wait_for(tool.fn(ctx, **block["input"]), timeout=timeout_s)
            outcome, result = "ok", {"type": "tool_result", "tool_use_id": block["id"], "content": out}
        except ToolError as e:
            outcome, result = (
                "error",
                {"type": "tool_result", "tool_use_id": block["id"], "content": str(e), "is_error": True},
            )
        except TimeoutError:
            msg = f"{name} timed out. Try again once, then apologise and offer a teammate."
            outcome, result = (
                "timeout",
                {"type": "tool_result", "tool_use_id": block["id"], "content": msg, "is_error": True},
            )
        if outcome != "ok":
            span.set_status(Status(StatusCode.ERROR, outcome))
            span.set_attribute("error.type", outcome)
        span.set_attribute("relay.tool.result_chars", len(str(result["content"])))
        metrics.tool_calls.labels(tool=name if tool else "unknown", outcome=outcome).inc()
        return result


async def call_model(llm: LLM, **kwargs) -> LLMResponse:
    model = getattr(llm, "model", "unknown")
    with tracer.start_as_current_span(f"chat {model}") as span:
        span.set_attributes(
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "anthropic",
                "gen_ai.request.model": model,
            }
        )
        resp = await llm.respond(**kwargs)
        served_by = resp.usage.get("model", model) if isinstance(resp.usage.get("model"), str) else model
        u = {k: v for k, v in resp.usage.items() if isinstance(v, int)}
        span.set_attributes(
            {
                "gen_ai.response.model": served_by,
                "gen_ai.response.finish_reasons": [resp.stop_reason],
                "gen_ai.usage.input_tokens": u.get("input_tokens", 0),
                "gen_ai.usage.output_tokens": u.get("output_tokens", 0),
                "gen_ai.usage.cache_read.input_tokens": u.get("cache_read_input_tokens", 0),
                "gen_ai.usage.cache_write.input_tokens": u.get("cache_creation_input_tokens", 0),
            }
        )
        record_content(span, "gen_ai.output.messages", _text(resp.content))
        metrics.llm_calls.labels(model=served_by, finish=resp.stop_reason).inc()
        metrics.llm_cost.labels(model=served_by).inc(cost_usd(u, served_by))
        for kind, key in (
            ("input", "input_tokens"),
            ("cache_read", "cache_read_input_tokens"),
            ("cache_write", "cache_creation_input_tokens"),
            ("output", "output_tokens"),
        ):
            metrics.llm_tokens.labels(model=served_by, kind=kind).inc(u.get(key, 0))
        return resp


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
    with tracer.start_as_current_span("invoke_agent relay") as span:
        span.set_attributes(
            {
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.agent.name": "relay",
                "gen_ai.conversation.id": str(ctx.session_id or ""),
                "relay.channel_tiers": ",".join(sorted(ctx.allowed_tiers)),
            }
        )
        result = await _run_turn(ctx, llm, system, history, on_text, guard, rewrites)
        span.set_attributes(
            {
                "relay.steps": result.steps,
                "relay.stopped": result.stopped or "",
                "relay.guard_failures": len(result.guard_failures),
            }
        )
        metrics.steps.observe(result.steps)
        if result.stopped:
            metrics.stopped.labels(reason=result.stopped).inc()
            span.set_status(Status(StatusCode.ERROR, result.stopped))
        return result


async def _run_turn(
    ctx: Context,
    llm: LLM,
    system: str,
    history: list[dict],
    on_text: OnText,
    guard: Guard | None,
    rewrites: int,
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
        resp = await call_model(
            llm,
            system=system,
            tools=specs(ctx.allowed_tiers, ctx.disabled_tools),
            messages=messages,
            on_text=hold if guard else on_text,
        )
        result.steps += 1
        result.usage.update({k: v for k, v in resp.usage.items() if isinstance(v, int)})
        result.cost_usd += cost_usd(resp.usage, resp.usage.get("model") or getattr(llm, "model", ""))
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
        for p in problems:
            kind = (
                "citation"
                if p.startswith("cites")
                else "refund_promise"
                if "refund" in p
                else "card"
                if "card" in p
                else "other"
            )
            metrics.guardrail_fires.labels(kind=kind).inc()
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
