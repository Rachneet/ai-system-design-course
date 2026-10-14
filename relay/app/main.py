"""Relay API.

POST /chat                      stream a reply over server-sent events (customers)
GET  /sessions/{id}             a session's transcript (its owner only)
POST /emails                    triage an inbound email and draft a reply for review (assist mode)
GET  /approvals                 pending refund approvals (staff)
POST /approvals/{id}/decision   approve or reject; send an Idempotency-Key header (staff)
GET  /healthz, /readyz          liveness and readiness
"""

import asyncio
import json
import random
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response

from . import approvals, metrics, online
from .agent import run_turn
from .auth import Principal, current_principal, staff_only
from .channels import handle_email
from .config import settings
from .db import NotFound, Store, open_pool
from .flags import Flags
from .guardrails import check_reply, redact_cards, sanitize_output
from .limits import enforce_budget, enforce_rate, record_usage
from .prompts import system_prompt
from .retrieval import Retriever
from .router import SIMPLE_TIERS, is_simple
from .telemetry import setup as setup_tracing
from .telemetry import tracer
from .tools import Context
from .wiring import (
    build_embedder,
    build_llm,
    build_quarantine,
    build_reranker,
    build_router,
    build_shipping,
    build_small_llm,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tests set app.state attributes before startup to swap in fakes; anything unset is built from settings.
    pool = None
    if not hasattr(app.state, "store"):
        pool = await open_pool(settings.database_url)
        app.state.store = Store(pool)
        await app.state.store.apply_schema()  # idempotent; run `python -m app.migrate` as a release step too
    if not hasattr(app.state, "llm"):
        app.state.llm = build_llm()
    if not hasattr(app.state, "quarantine"):
        app.state.quarantine = build_quarantine()
    if not hasattr(app.state, "retriever"):
        app.state.retriever = Retriever(app.state.store, build_embedder(), build_reranker())
    for name, build in (
        ("small_llm", build_small_llm),
        ("router", build_router),
        ("shipping", build_shipping),
    ):
        if not hasattr(app.state, name):
            setattr(app.state, name, build())
    setup_tracing("relay-api")
    yield
    if pool is not None:
        await pool.close()


app = FastAPI(title="Relay", lifespan=lifespan)


def state(request: Request, name: str):
    """App state with safe defaults, so tests can inject only what they need."""
    flags = getattr(request.app.state, "flags", None)
    if name == "flags" and (flags is None or flags.store is not request.app.state.store):
        request.app.state.flags = Flags(request.app.state.store)
    return getattr(request.app.state, name, None)


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID | None = None
    message: str = Field(min_length=1, max_length=4000)


def sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


@app.post("/chat")
async def chat(body: ChatIn, request: Request, who: Principal = Depends(current_principal)):
    store: Store = request.app.state.store
    await enforce_rate(store, who.customer_id, settings.messages_per_minute, settings.message_burst)
    await enforce_budget(store, who.customer_id, settings.daily_token_budget)
    flags = await state(request, "flags").all()
    if not flags["agent.enabled"]:  # kill switch: pause the assistant without a deploy
        paused = "Our assistant is paused right now. Please email support@northwind.example and we'll reply within a day."
        return StreamingResponse(
            iter([sse({"text": paused}), sse({"done": True, "paused": True})]), media_type="text/event-stream"
        )
    session_id = body.session_id or uuid4()
    try:
        history = await store.load_session(session_id, who.customer_id, create=True)
    except NotFound:
        raise HTTPException(404, "Session not found") from None
    text, _ = redact_cards(body.message)  # before it is stored, logged, or sent to the model
    user_msg = {"role": "user", "content": [{"type": "text", "text": text}]}
    now = datetime.now(UTC)
    ctx = Context(
        store=store,
        customer_id=who.customer_id,
        session_id=session_id,
        now=now,
        retriever=request.app.state.retriever,
        staff=who.staff,
        quarantine=request.app.state.quarantine,
        shipping=state(request, "shipping"),
        disabled_tools=frozenset(flags["tools.disabled"]),
    )
    system = system_prompt(await store.memories(who.customer_id), now)
    llm = request.app.state.llm
    if hasattr(llm, "force_fallback"):
        llm.force_fallback = bool(flags["agent.force_fallback"])
    route = "full"
    router = state(request, "router")
    if flags["routing.enabled"] and router is not None and is_simple(await router.classify(text)):
        route, llm, ctx.allowed_tiers = "simple", state(request, "small_llm"), SIMPLE_TIERS
    metrics.routes.labels(route=route).inc()

    def guard(draft: str, result) -> list[str]:
        return check_reply(draft, ctx.retrieved, result.tool_calls)

    async def events():
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def on_text(t: str) -> None:
            await queue.put(sanitize_output(t))  # guarded mode emits whole drafts, so links are never split

        async def work():
            try:
                with tracer.start_as_current_span("POST /chat turn") as span:
                    span.set_attributes(
                        {
                            "relay.route": route,
                            "gen_ai.conversation.id": str(session_id),
                            "enduser.pseudo.id": who.customer_id,
                        }
                    )  # pseudonymous ID, never an email
                    return await run_turn(ctx, llm, system, [*history, user_msg], on_text, guard=guard)
            finally:
                await queue.put(None)

        started, first = time.perf_counter(), None
        task = asyncio.create_task(work())
        try:
            while (chunk := await queue.get()) is not None:
                if first is None:
                    first = time.perf_counter() - started
                    metrics.ttft.observe(first)
                yield sse({"text": chunk})
            result = await task
        except asyncio.CancelledError:  # client disconnected: stop paying for an answer nobody will read
            task.cancel()
            metrics.turns.labels(outcome="cancelled").inc()
            raise
        except Exception:
            metrics.turns.labels(outcome="error").inc()
            yield sse({"error": "Something went wrong. Please try again.", "session_id": str(session_id)})
            raise
        metrics.turn_seconds.observe(time.perf_counter() - started)
        metrics.turns.labels(outcome="stopped" if result.stopped else "ok").inc()
        await store.save_turn(
            session_id,
            who.customer_id,
            len(history),
            [user_msg, *result.new_messages],
            memory_delay_s=settings.memory_idle_s,
            judge=random.random() < settings.online_judge_rate,
        )
        await record_usage(store, who.customer_id, sum(result.usage.values()), result.cost_usd)
        yield sse(
            {"done": True, "session_id": str(session_id), "steps": result.steps, "stopped": result.stopped}
        )

    return StreamingResponse(events(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


@app.get("/sessions/{session_id}")
async def get_session(session_id: UUID, request: Request, who: Principal = Depends(current_principal)):
    try:
        messages = await request.app.state.store.load_session(session_id, who.customer_id)
    except NotFound:
        raise HTTPException(404, "Session not found") from None
    return {"session_id": session_id, "messages": messages}


class EmailIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(max_length=300)
    body: str = Field(min_length=1, max_length=20_000)


@app.post("/emails")
async def inbound_email(body: EmailIn, request: Request, who: Principal = Depends(current_principal)):
    """Triage an inbound email and draft a reply for a human to review (assist mode). Nothing is sent."""
    store: Store = request.app.state.store
    await enforce_rate(store, who.customer_id, settings.messages_per_minute, settings.message_burst)
    ctx = Context(
        store=store,
        customer_id=who.customer_id,
        now=datetime.now(UTC),
        retriever=request.app.state.retriever,
        quarantine=request.app.state.quarantine,
    )
    outcome = await handle_email(ctx, request.app.state.llm, body.subject, redact_cards(body.body)[0])
    return {
        "triage": outcome.triage.model_dump(),
        "draft": outcome.draft,
        "stopped": outcome.result.stopped if outcome.result else None,
    }


@app.get("/approvals")
async def list_approvals(request: Request, _: Principal = Depends(staff_only)):
    return {"approvals": await approvals.pending(request.app.state.store)}


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]


@app.post("/approvals/{approval_id}/decision")
async def decide(
    approval_id: int,
    body: DecisionIn,
    request: Request,
    who: Principal = Depends(staff_only),
    idempotency_key: str | None = Header(default=None, max_length=100),
):
    store = request.app.state.store

    async def run():
        return await approvals.decide(store, approval_id, body.decision == "approve", who.customer_id)

    status, payload = await approvals.idempotent(
        store, who.customer_id, idempotency_key, {"approval": approval_id, **body.model_dump()}, run
    )
    return JSONResponse(payload, status_code=status)


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID
    rating: Literal["up", "down"]
    reason: Literal["wrong_info", "did_not_do_it", "too_long", "unsafe", "other"] | None = None
    comment: str | None = Field(default=None, max_length=2000)


@app.post("/feedback", status_code=204)
async def feedback(body: FeedbackIn, request: Request, who: Principal = Depends(current_principal)):
    store: Store = request.app.state.store
    try:
        await store.load_session(body.session_id, who.customer_id)  # only rate your own conversations
    except NotFound:
        raise HTTPException(404, "Session not found") from None
    from .jobs import enqueue

    async with store.conn() as c, c.transaction():
        await c.execute(
            "INSERT INTO feedback (session_id, customer_id, rating, reason, comment) VALUES (%s, %s, %s, %s, %s)",
            (
                body.session_id,
                who.customer_id,
                body.rating,
                body.reason,
                redact_cards(body.comment)[0] if body.comment else None,
            ),
        )
        if body.rating == "down":  # every thumbs-down is judged and lands in the review queue
            await enqueue(
                c,
                "judge_session",
                f"{body.session_id}:feedback",
                {"session_id": str(body.session_id), "customer_id": who.customer_id, "trigger": "feedback"},
            )
    metrics.feedback.labels(rating=body.rating).inc()
    return Response(status_code=204)


@app.get("/review-queue")
async def review_queue(request: Request, _: Principal = Depends(staff_only)):
    return {"items": await online.review_queue(request.app.state.store)}


@app.get("/flags")
async def get_flags(request: Request, _: Principal = Depends(staff_only)):
    return await state(request, "flags").all()


class FlagIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: Literal["tools.disabled", "agent.enabled", "agent.force_fallback", "routing.enabled"]
    value: bool | list[str]


@app.put("/flags")
async def set_flag(body: FlagIn, request: Request, who: Principal = Depends(staff_only)):
    await state(request, "flags").set(body.key, body.value, who.customer_id)
    return await state(request, "flags").all()


@app.get("/metrics")
async def prometheus_metrics():
    # Expose on an internal port or restrict at the load balancer in production.
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/healthz")
async def healthz():
    return {"ok": True}  # liveness only: never check dependencies here


@app.get("/readyz")
async def readyz(request: Request):
    try:
        async with request.app.state.store.conn() as c:
            await c.execute("SELECT 1")
    except Exception as e:
        raise HTTPException(503, "database unavailable") from e
    return {"ok": True}  # deliberately does not call the model provider
