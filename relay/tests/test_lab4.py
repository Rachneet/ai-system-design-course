import asyncio

import httpx
import pytest

from app import approvals, limits, main
from app.auth import Verifier, get_verifier
from app.config import Settings
from app.jobs import enqueue, run_ready
from app.main import app
from app.tools import request_refund_approval
from app.worker import health_server
from scripts.dev_token import mint
from tests.fakes import FakeQuarantine, ScriptedLLM, text
from tests.test_api import SECRET, token


@pytest.fixture
def client(store, retriever, monkeypatch):
    app.state.store, app.state.retriever, app.state.quarantine = store, retriever, FakeQuarantine()
    app.dependency_overrides[get_verifier] = lambda: Verifier(
        Settings(auth_mode="dev", dev_jwt_secret=SECRET)
    )
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://relay")
    app.dependency_overrides.clear()


def test_verifier_refuses_to_start_misconfigured():
    with pytest.raises(RuntimeError):
        Verifier(Settings(auth_mode="jwt", jwks_url="", jwt_issuer=""))
    with pytest.raises(RuntimeError):
        Verifier(Settings(auth_mode="dev", dev_jwt_secret="short"))
    with pytest.raises(RuntimeError):
        Verifier(Settings(auth_mode="none"))


def test_staff_role_comes_from_the_token():
    v = Verifier(Settings(auth_mode="dev", dev_jwt_secret=SECRET))
    assert v.verify(mint("s_1", staff=True, secret=SECRET)).staff
    assert not v.verify(mint("c_77", secret=SECRET)).staff


async def test_token_bucket(store):
    assert [await limits.take(store, "k", rate_per_s=1, burst=3) for _ in range(3)] == [0, 0, 0]
    wait = await limits.take(store, "k", rate_per_s=1, burst=3)
    assert 0 < wait <= 1


async def test_rate_limit_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(main.settings, "message_burst", 2)
    app.state.llm = ScriptedLLM(text("a"), text("b"))
    codes = [
        (await client.post("/chat", json={"message": "hi"}, headers=token("c_77"))).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]
    r = await client.post("/chat", json={"message": "hi"}, headers=token("c_77"))
    assert int(r.headers["Retry-After"]) >= 1


async def test_daily_token_budget(client, store, monkeypatch):
    monkeypatch.setattr(main.settings, "daily_token_budget", 100)
    await limits.record_usage(store, "c_77", 150, 0.01)
    r = await client.post("/chat", json={"message": "hi"}, headers=token("c_77"))
    assert r.status_code == 429 and "usage limit" in r.json()["detail"]


async def test_approval_flow_is_staff_only_and_idempotent(client, store, ctx):
    created = await request_refund_approval(ctx, 3001, 640.0, "broken pole")
    approval_id = int(created.split("#")[1].split()[0])
    listed = await client.get("/approvals", headers=token("c_77"))
    assert listed.status_code == 403
    pending = (await client.get("/approvals", headers=token("s_1", staff=True))).json()["approvals"]
    assert [a["id"] for a in pending] == [approval_id]

    headers = token("s_1", staff=True) | {"Idempotency-Key": "decide-1"}
    first = await client.post(
        f"/approvals/{approval_id}/decision", json={"decision": "approve"}, headers=headers
    )
    retry = await client.post(
        f"/approvals/{approval_id}/decision", json={"decision": "approve"}, headers=headers
    )
    assert first.status_code == retry.status_code == 200 and first.json() == retry.json()
    assert first.json()["status"] == "executed" and float((await store.refund_for(3001))["amount"]) == 640
    misuse = await client.post(
        f"/approvals/{approval_id}/decision", json={"decision": "reject"}, headers=headers
    )
    assert misuse.status_code == 422
    again = await client.post(
        f"/approvals/{approval_id}/decision",
        json={"decision": "reject"},
        headers=token("s_1", staff=True) | {"Idempotency-Key": "decide-2"},
    )
    assert again.status_code == 409


async def test_concurrent_approvals_execute_once(store, ctx):
    created = await request_refund_approval(ctx, 3001, 640.0, "broken pole")
    approval_id = int(created.split("#")[1].split()[0])
    results = await asyncio.gather(
        *(approvals.decide(store, approval_id, True, "s_1") for _ in range(3)), return_exceptions=True
    )
    assert sum(isinstance(r, dict) for r in results) == 1


async def test_jobs_are_debounced_and_retried(store):
    calls = []

    async def flaky(payload):
        calls.append(payload)
        if len(calls) == 1:
            raise RuntimeError("model timeout")

    async with store.conn() as c:
        await enqueue(c, "extract_memory", "s1", {"n": 1})
        await enqueue(c, "extract_memory", "s1", {"n": 2})  # same session: replaces, does not duplicate
    assert await run_ready(store, {"extract_memory": flaky}) == 1 and calls == [{"n": 2}]
    async with store.conn() as c:
        await c.execute("UPDATE jobs SET run_after = now() WHERE status = 'queued'")
    assert await run_ready(store, {"extract_memory": flaky}) == 1 and len(calls) == 2


async def test_worker_health_endpoint():
    server = await health_server(0)
    port = server.sockets[0].getsockname()[1]
    async with httpx.AsyncClient() as c:
        assert (await c.get(f"http://127.0.0.1:{port}/healthz")).json() == {"ok": True}
    server.close()
