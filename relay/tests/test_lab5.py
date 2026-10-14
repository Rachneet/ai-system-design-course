import anthropic
import httpx
import pytest
from mcp.server.mcpserver import MCPServer
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import agent, main
from app.flags import Flags
from app.jobs import run_ready
from app.judges import Verdict
from app.main import app
from app.resilience import CircuitBreaker, FaultInjectingLLM, InjectedFault, ResilientLLM
from app.shipping import ShippingClient
from app.tools import track_package
from app.worker import handlers, health_server
from mcp_servers.shipping import server as shipping_server
from tests.fakes import FakeExtractor, ScriptedLLM, text, tool_use
from tests.test_api import token
from tests.test_lab4 import client  # noqa: F401 - shared fixture

SPANS = InMemorySpanExporter()


@pytest.fixture(scope="module", autouse=True)
def tracing():
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(SPANS))
    trace.set_tracer_provider(provider)  # a process-wide default; set once
    yield


@pytest.fixture(autouse=True)
def clear_spans():
    SPANS.clear()


def spans_by_name():
    return {s.name: s for s in SPANS.get_finished_spans()}


async def test_a_turn_is_one_trace_with_genai_attributes(ctx):
    llm = ScriptedLLM(
        tool_use(("get_order", {"order_id": 1042}), ("search_kb", {"query": "return window"})),
        text("Delivered, and you have 60 days to return it."),
    )
    llm.model, llm.provider = "claude-haiku-5-5", "gemini"
    await agent.run_turn(ctx, llm, "s", [{"role": "user", "content": "hi"}], noop)
    spans = spans_by_name()
    root, chat = spans["invoke_agent relay"], spans["chat claude-haiku-5-5"]
    tool, retrieval = spans["execute_tool get_order"], spans["retrieval.search"]
    assert {s.context.trace_id for s in SPANS.get_finished_spans()} == {root.context.trace_id}
    assert chat.parent.span_id == root.context.span_id and tool.parent.span_id == root.context.span_id
    assert retrieval.parent.span_id == spans["execute_tool search_kb"].context.span_id
    assert (
        chat.attributes["gen_ai.operation.name"] == "chat"
        and chat.attributes["gen_ai.usage.input_tokens"] == 100
        and chat.attributes["gen_ai.provider.name"]
        == "gcp.gemini"  # OTel's well-known name, not Relay's prefix
    )
    assert tool.attributes["gen_ai.tool.name"] == "get_order" and root.attributes["relay.steps"] == 2
    assert "gen_ai.output.messages" not in chat.attributes  # content is opt-in


async def test_mcp_call_joins_the_callers_trace(ctx):
    seen = {}

    probe = MCPServer("probe")

    @probe.tool()
    async def track_package(tracking_number: str) -> dict:
        seen["trace_id"] = trace.get_current_span().get_span_context().trace_id
        return {"status": "in_transit", "last_scan": "2026-10-01 08:00 UTC", "location": "Denver, CO"}

    ctx.shipping = ShippingClient(probe)
    with trace.get_tracer("test").start_as_current_span("caller") as caller:
        out = await track_package_tool(ctx)
    assert "in_transit" in out
    assert seen["trace_id"] == caller.get_span_context().trace_id  # traceparent travelled in params._meta
    assert "mcp.client shipping.track_package" in spans_by_name()


async def track_package_tool(ctx):
    async with ctx.store.conn() as c:
        await c.execute("UPDATE orders SET status = 'shipped', tracking_number = 'NW1042' WHERE id = 1042")
    return await track_package(ctx, 1042)


async def test_real_shipping_server_and_scoping(ctx):
    ctx.shipping = ShippingClient(shipping_server)
    assert "Carrier status for order 1042" in await track_package_tool(ctx)
    from app.tools import ToolError

    with pytest.raises(ToolError):
        await track_package(ctx, 2210)  # another customer's order


class FlakyLLM:
    model = "claude-opus-5-5"

    def __init__(self, failures: int, emit_first: bool = False):
        self.failures, self.calls, self.emit_first = failures, 0, emit_first

    async def respond(self, *, system, tools, messages, on_text):
        self.calls += 1
        if self.emit_first:
            await on_text("partial ")
        if self.calls <= self.failures:
            raise InjectedFault("boom")
        return text("primary ok")


async def no_sleep(_):
    return None


async def noop(_):
    return None


async def test_retries_then_succeeds():
    llm = ResilientLLM(FlakyLLM(2), ScriptedLLM(text("fallback")), attempts=3, sleep=no_sleep)
    resp = await llm.respond(system="", tools=[], messages=[], on_text=noop)
    assert resp.content[0]["text"] == "primary ok" and llm.primary.calls == 3


async def test_falls_back_after_retries_and_breaker_opens():
    breaker = CircuitBreaker(threshold=3, reset_after_s=60)
    fallback = ScriptedLLM(text("fallback 1"), text("fallback 2"))
    fallback.model = "claude-haiku-5-5"
    llm = ResilientLLM(FlakyLLM(99), fallback, attempts=3, breaker=breaker, sleep=no_sleep)
    first = await llm.respond(system="", tools=[], messages=[], on_text=noop)
    assert first.usage["model"] == "claude-haiku-5-5" and breaker.state == "open"
    calls_before = llm.primary.calls
    await llm.respond(system="", tools=[], messages=[], on_text=noop)
    assert llm.primary.calls == calls_before  # open breaker: no waiting on a dead provider


async def test_no_retry_after_text_was_streamed():
    llm = ResilientLLM(FlakyLLM(1, emit_first=True), ScriptedLLM(text("x")), sleep=no_sleep)
    with pytest.raises(InjectedFault):
        await llm.respond(system="", tools=[], messages=[], on_text=noop)


def test_breaker_half_open_after_reset():
    now = [0.0]
    b = CircuitBreaker(threshold=1, reset_after_s=10, clock=lambda: now[0])
    b.failure()
    assert b.state == "open" and not b.allow()
    now[0] = 11
    assert b.state == "half_open" and b.allow()
    b.failure()
    assert b.state == "open"


def test_retryable_includes_rate_limits():
    from app.resilience import RETRYABLE

    assert anthropic.RateLimitError in RETRYABLE and anthropic.APIConnectionError in RETRYABLE


async def test_fault_injection_rate():
    import random

    llm = FaultInjectingLLM(ScriptedLLM(*[text("ok")] * 100), rate=0.5, rng=random.Random(1))
    outcomes = []
    for _ in range(100):
        try:
            await llm.respond(system="", tools=[], messages=[], on_text=noop)
            outcomes.append(True)
        except InjectedFault:
            outcomes.append(False)
    assert 35 < outcomes.count(False) < 65


async def test_kill_switches(client, store, monkeypatch):  # noqa: F811
    staff = token("s_1", staff=True)
    r = await client.put("/flags", json={"key": "tools.disabled", "value": ["issue_refund"]}, headers=staff)
    assert r.json()["tools.disabled"] == ["issue_refund"]
    app.state.llm = ScriptedLLM(
        tool_use(("issue_refund", {"order_id": 1042, "amount": 45.0, "reason": "x"})), text("ok")
    )
    await client.post("/chat", json={"message": "refund 1042"}, headers=token("c_77"))
    assert "issue_refund" not in {t["name"] for t in app.state.llm.requests[0]["tools"]}
    assert await store.refund_for(1042) is None
    await client.put("/flags", json={"key": "agent.enabled", "value": False}, headers=staff)
    r = await client.post("/chat", json={"message": "hi"}, headers=token("c_77"))
    assert "paused" in r.text
    assert (
        await client.put("/flags", json={"key": "agent.enabled", "value": True}, headers=token("c_77"))
    ).status_code == 403


async def test_flags_cache_expires(store):
    now = [0.0]
    a, b = Flags(store, ttl_s=10, clock=lambda: now[0]), Flags(store, ttl_s=10, clock=lambda: now[0])
    assert await b.get("agent.enabled") is True
    await a.set("agent.enabled", False, "s_1")
    assert await a.get("agent.enabled") is False and await b.get("agent.enabled") is True  # b still cached
    now[0] = 11
    assert await b.get("agent.enabled") is False


async def test_routing_sends_simple_intents_to_the_small_model(client, monkeypatch):  # noqa: F811
    class Router:
        async def classify(self, message):
            return "order_status"

    app.state.router = Router()
    app.state.small_llm = ScriptedLLM(text("small model"))
    app.state.llm = ScriptedLLM(text("big model"))
    await client.put(
        "/flags", json={"key": "routing.enabled", "value": True}, headers=token("s_1", staff=True)
    )
    r = await client.post("/chat", json={"message": "where is 7001"}, headers=token("c_77"))
    assert "small model" in r.text
    tools = {t["name"] for t in app.state.small_llm.requests[0]["tools"]}
    assert "issue_refund" not in tools and "escalate_to_human" in tools
    del app.state.router, app.state.small_llm


class PassFailJudge:
    async def judge(self, name, transcript):
        return Verdict(reasoning="promised a refund without a tool result", verdict="fail")


async def test_thumbs_down_is_judged_and_queued_for_review(client, store, monkeypatch):  # noqa: F811
    monkeypatch.setattr(main.settings, "online_judge_rate", 0.0)
    app.state.llm = ScriptedLLM(text("Your refund is on its way!"))
    r = await client.post("/chat", json={"message": "refund?"}, headers=token("c_77"))
    sid = (
        next(line for line in r.text.splitlines() if '"done"' in line)
        .split('"session_id": "')[1]
        .split('"')[0]
    )
    fb = await client.post(
        "/feedback", json={"session_id": sid, "rating": "down", "reason": "wrong_info"}, headers=token("c_77")
    )
    assert fb.status_code == 204
    other = await client.post("/feedback", json={"session_id": sid, "rating": "up"}, headers=token("c_91"))
    assert other.status_code == 404
    async with store.conn() as c:
        await c.execute("UPDATE jobs SET run_after = now()")
    await run_ready(store, handlers(store, FakeExtractor([]), PassFailJudge()))
    queue = (await client.get("/review-queue", headers=token("s_1", staff=True))).json()["items"]
    assert {i["source"] for i in queue} == {"judge", "feedback"}


async def test_metrics_endpoints(client):  # noqa: F811
    app.state.llm = ScriptedLLM(text("hello"))
    await client.post("/chat", json={"message": "hi"}, headers=token("c_77"))
    body = (await client.get("/metrics")).text
    assert (
        "relay_chat_turns_total" in body
        and "relay_ttft_seconds_bucket" in body
        and "relay_llm_tokens_total" in body
    )
    server = await health_server(0)
    port = server.sockets[0].getsockname()[1]
    async with httpx.AsyncClient() as c:
        assert "relay_jobs_total" in (await c.get(f"http://127.0.0.1:{port}/metrics")).text
    server.close()


def test_trace_redaction_masks_phones_but_not_plain_ids():
    from app.telemetry import redact

    out = redact("call +44 20 7946 0958 or (555) 123-4567 about order 1042, ref 1234567890, ts 20261014")
    assert out.count("[PHONE]") == 2
    assert "1042" in out and "1234567890" in out and "20261014" in out
