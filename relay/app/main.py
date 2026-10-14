"""Relay API: POST /chat streams a reply over server-sent events and persists every message."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .agent import run_turn
from .channels import handle_email
from .config import settings
from .db import NotFound, Store, open_pool
from .guardrails import check_reply, redact_cards, sanitize_output
from .llm import AnthropicLLM
from .memory import AnthropicExtractor, remember
from .prompts import system_prompt
from .quarantine import AnthropicQuarantine
from .retrieval import Retriever
from .tools import Context


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tests set app.state.store / llm / extractor before startup to swap in fakes.
    pool = None
    if not hasattr(app.state, "store"):
        pool = await open_pool(settings.database_url)
        app.state.store = Store(pool)
        await app.state.store.apply_schema()
    if not hasattr(app.state, "llm"):
        app.state.llm = AnthropicLLM(settings.model, settings.max_tokens, settings.refusal_fallback)
    if not hasattr(app.state, "extractor"):
        app.state.extractor = AnthropicExtractor(settings.memory_model)
    if not hasattr(app.state, "quarantine"):
        app.state.quarantine = AnthropicQuarantine(settings.memory_model)
    if not hasattr(app.state, "retriever"):
        from .embeddings import LocalEmbedder, LocalReranker  # loads local models; tests inject fakes instead

        app.state.retriever = Retriever(app.state.store, LocalEmbedder(), LocalReranker())
    yield
    if pool is not None:
        await pool.close()


app = FastAPI(title="Relay", lifespan=lifespan)


async def current_customer(x_customer_id: str = Header(min_length=1, max_length=64)) -> str:
    # Labs 1-3 trust headers. Lab 4 replaces them with JWT verification. Never let the model choose identity.
    return x_customer_id


async def is_staff(x_role: str | None = Header(default=None)) -> bool:
    return x_role == "staff"


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID | None = None
    message: str = Field(min_length=1, max_length=4000)


def sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


@app.post("/chat")
async def chat(
    body: ChatIn,
    request: Request,
    bg: BackgroundTasks,
    customer_id: str = Depends(current_customer),
    staff: bool = Depends(is_staff),
):
    store: Store = request.app.state.store
    session_id = body.session_id or uuid4()
    try:
        history = await store.load_session(session_id, customer_id, create=True)
    except NotFound:
        raise HTTPException(404, "Session not found")
    text, _ = redact_cards(body.message)  # before it is stored, logged, or sent to the model
    user_msg = {"role": "user", "content": [{"type": "text", "text": text}]}
    now = datetime.now(UTC)
    ctx = Context(
        store=store,
        customer_id=customer_id,
        session_id=session_id,
        now=now,
        retriever=request.app.state.retriever,
        staff=staff,
        quarantine=request.app.state.quarantine,
    )

    def guard(draft: str, result) -> list[str]:
        return check_reply(draft, ctx.retrieved, result.tool_calls)

    system = system_prompt(await store.memories(customer_id), now)

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
        while (chunk := await queue.get()) is not None:
            yield sse({"text": chunk})
        try:
            result = await task
        except Exception:
            yield sse({"error": "Something went wrong. Please try again.", "session_id": str(session_id)})
            raise
        await store.append_messages(session_id, len(history), [user_msg, *result.new_messages])
        yield sse(
            {"done": True, "session_id": str(session_id), "steps": result.steps, "stopped": result.stopped}
        )

    # Runs after the stream finishes. Lab 4 moves this to a worker that waits until the session is idle.
    bg.add_task(remember_session, store, request.app.state.extractor, customer_id, session_id)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


async def remember_session(store: Store, extractor, customer_id: str, session_id: UUID) -> None:
    messages = await store.load_session(session_id, customer_id)
    await remember(store, extractor, customer_id, session_id, messages)


class EmailIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(max_length=300)
    body: str = Field(min_length=1, max_length=20_000)


@app.post("/emails")
async def inbound_email(body: EmailIn, request: Request, customer_id: str = Depends(current_customer)):
    """Triage an inbound email and draft a reply for a human to review (assist mode). Nothing is sent."""
    ctx = Context(
        store=request.app.state.store,
        customer_id=customer_id,
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


@app.get("/sessions/{session_id}")
async def get_session(session_id: UUID, request: Request, customer_id: str = Depends(current_customer)):
    try:
        return {
            "session_id": session_id,
            "messages": await request.app.state.store.load_session(session_id, customer_id),
        }
    except NotFound:
        raise HTTPException(404, "Session not found")


@app.get("/healthz")
async def healthz():
    return {"ok": True}
