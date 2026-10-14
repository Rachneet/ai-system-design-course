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
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from . import approvals
from .agent import run_turn
from .auth import Principal, current_principal, staff_only
from .channels import handle_email
from .config import settings
from .db import NotFound, Store, open_pool
from .guardrails import check_reply, redact_cards, sanitize_output
from .limits import enforce_budget, enforce_rate, record_usage
from .prompts import system_prompt
from .retrieval import Retriever
from .tools import Context
from .wiring import build_embedder, build_llm, build_quarantine, build_reranker

PRICES = {  # USD per million tokens (input, cache write, cache read, output), checked 2026-10-14
    "claude-opus-5-5": (4.00, 5.00, 0.20, 20.00),
    "claude-sonnet-5-5": (2.00, 2.50, 0.10, 10.00),
    "claude-haiku-5-5": (0.10, 0.125, 0.01, 0.50),
}


def cost_usd(usage: dict) -> float:
    p_in, p_write, p_read, p_out = PRICES.get(settings.model, (0, 0, 0, 0))
    return (
        usage.get("input_tokens", 0) * p_in
        + usage.get("cache_creation_input_tokens", 0) * p_write
        + usage.get("cache_read_input_tokens", 0) * p_read
        + usage.get("output_tokens", 0) * p_out
    ) / 1e6


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
    yield
    if pool is not None:
        await pool.close()


app = FastAPI(title="Relay", lifespan=lifespan)


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
    )
    system = system_prompt(await store.memories(who.customer_id), now)

    def guard(draft: str, result) -> list[str]:
        return check_reply(draft, ctx.retrieved, result.tool_calls)

    async def events():
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def on_text(t: str) -> None:
            await queue.put(sanitize_output(t))  # guarded mode emits whole drafts, so links are never split

        async def work():
            try:
                return await run_turn(
                    ctx, request.app.state.llm, system, [*history, user_msg], on_text, guard=guard
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(work())
        try:
            while (chunk := await queue.get()) is not None:
                yield sse({"text": chunk})
            result = await task
        except asyncio.CancelledError:  # client disconnected: stop paying for an answer nobody will read
            task.cancel()
            raise
        except Exception:
            yield sse({"error": "Something went wrong. Please try again.", "session_id": str(session_id)})
            raise
        await store.save_turn(
            session_id,
            who.customer_id,
            len(history),
            [user_msg, *result.new_messages],
            memory_delay_s=settings.memory_idle_s,
        )
        usage = dict(result.usage)
        await record_usage(store, who.customer_id, sum(usage.values()), cost_usd(usage))
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
