import asyncio
import json

from tests.conftest import ADMIN, msg, provision


async def ledger(client, sql: str):
    async with client.app.state.pool.connection() as c:
        return await (await c.execute(sql)).fetchall()


async def settle(client):
    await client.app.state.gateway.drain()


async def test_admin_api_requires_the_admin_token(gw):
    assert (await gw.post("/admin/orgs", json={"id": "acme", "name": "Acme"})).status_code == 401
    bad = {"Authorization": "Bearer wrong"}
    assert (await gw.post("/admin/orgs", json={"id": "acme", "name": "Acme"}, headers=bad)).status_code == 401


async def test_keys_are_shown_once_and_stored_hashed(gw):
    key = await provision(gw)
    assert key.startswith("sbk_")
    rows = await ledger(gw, "SELECT secret_hash FROM api_keys")
    assert key not in str(rows) and len(rows[0]["secret_hash"]) == 64


async def test_proxy_meters_and_charges_back(gw, upstream):
    key = await provision(gw)
    r = await gw.post("/v1/messages", json=msg(), headers={"x-api-key": key})
    assert r.status_code == 200 and r.json()["content"][0]["text"] == "echo from claude-sonnet-5-5"
    assert r.headers["x-switchboard-model"] == "claude-sonnet-5-5" and r.headers["x-request-id"].startswith("sbr_")
    assert upstream.state.headers[0]["x-api-key"] == "provider-secret"  # the app's key never reaches the provider
    await settle(gw)
    [event] = await ledger(gw, "SELECT * FROM usage_events")
    assert event["status"] == 200 and event["output_tokens"] == 12 and event["cost_usd"] > 0
    spend = await ledger(gw, "SELECT scope, requests FROM spend_monthly ORDER BY scope")
    assert [(s["scope"], s["requests"]) for s in spend] == [("app", 1), ("org", 1), ("team", 1)]
    report = (
        await gw.get("/admin/usage", params={"month": event["ts"].strftime("%Y-%m"), "group_by": "team"}, headers=ADMIN)
    ).json()
    assert report["rows"][0]["id"] == "cx" and report["rows"][0]["requests"] == 1


async def test_bodies_are_forwarded_byte_for_byte(gw, upstream):
    """Re-serialising JSON changes bytes and silently breaks prompt caching; the gateway must not do it."""
    key = await provision(gw, pii_mode="detect")
    raw = b'{"model":"claude-sonnet-5-5",  "max_tokens":100,"messages":[{"role":"user","content":"hi \\u00e9"}]}'
    await gw.post("/v1/messages", content=raw, headers={"x-api-key": key, "content-type": "application/json"})
    assert upstream.state.received[0] == raw


async def test_pii_redaction_and_audit(gw, upstream):
    key = await provision(gw, pii_mode="redact", log_bodies=True)
    text = "card 4111 1111 1111 1111, email ada@example.com, order 1042"
    await gw.post("/v1/messages", json=msg(text=text), headers={"x-api-key": key})
    sent = upstream.state.received[0].decode()
    assert "4111" not in sent and "ada@example.com" not in sent and "1042" in sent
    await settle(gw)
    [audit] = await ledger(gw, "SELECT request::text AS request, expires_at FROM audit_bodies")
    assert "4111" not in audit["request"] and "[CARD]" in audit["request"]
    [event] = await ledger(gw, "SELECT pii_findings FROM usage_events")
    assert event["pii_findings"] == 2


async def test_detect_mode_counts_but_forwards_unchanged(gw, upstream):
    key = await provision(gw, pii_mode="detect")
    await gw.post("/v1/messages", json=msg(text="mail me at ada@example.com"), headers={"x-api-key": key})
    assert b"ada@example.com" in upstream.state.received[0]


async def test_auth_policy_and_revocation(gw):
    key = await provision(gw, allowed_models=["claude-haiku-5-5"])
    assert (await gw.post("/v1/messages", json=msg(), headers={"x-api-key": "sbk_nope_x"})).status_code == 401
    assert (await gw.post("/v1/messages", json=msg(), headers={"x-api-key": key})).json()["error"][
        "type"
    ] == "permission_error"
    assert (await gw.post("/v1/messages", json=msg(model="gpt-9"), headers={"x-api-key": key})).status_code == 400
    ok = await gw.post("/v1/messages", json=msg(model="claude-haiku-5-5"), headers={"Authorization": f"Bearer {key}"})
    assert ok.status_code == 200
    key_id = key.split("_")[1]
    assert (await gw.delete(f"/admin/keys/{key_id}", headers=ADMIN)).status_code == 204
    assert (
        await gw.post("/v1/messages", json=msg(model="claude-haiku-5-5"), headers={"x-api-key": key})
    ).status_code == 401


async def test_request_rate_limit(gw):
    key = await provision(gw, rpm=2)
    codes = [(await gw.post("/v1/messages", json=msg(), headers={"x-api-key": key})).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    r = await gw.post("/v1/messages", json=msg(), headers={"x-api-key": key})
    assert int(r.headers["retry-after"]) >= 1 and r.json()["error"]["type"] == "rate_limit_error"


async def test_token_rate_limit_uses_max_tokens(gw):
    key = await provision(gw, tpm=1000)
    r = await gw.post("/v1/messages", json=msg(max_tokens=5000), headers={"x-api-key": key})
    assert r.status_code == 429 and "Token rate" in r.json()["error"]["message"]


async def test_budgets_stop_spend_at_every_level(gw):
    key = await provision(gw, budget_usd_month="0.0000001")
    assert (await gw.post("/v1/messages", json=msg(), headers={"x-api-key": key})).status_code == 200
    await settle(gw)
    r = await gw.post("/v1/messages", json=msg(), headers={"x-api-key": key})
    assert r.status_code == 429 and r.headers["x-switchboard-limit"] == "budget:app"


async def test_fallback_before_first_byte(gw, upstream):
    key = await provision(gw)
    upstream.state.fail = {"claude-opus-5-5": 529}
    r = await gw.post("/v1/messages", json=msg(model="claude-opus-5-5"), headers={"x-api-key": key})
    assert r.status_code == 200 and r.headers["x-switchboard-model"] == "claude-sonnet-5-5"
    await settle(gw)
    [event] = await ledger(gw, "SELECT requested_model, served_model, fallback FROM usage_events")
    assert event == {"requested_model": "claude-opus-5-5", "served_model": "claude-sonnet-5-5", "fallback": True}


async def test_no_fallback_to_a_model_the_app_may_not_use(gw, upstream):
    key = await provision(gw, allowed_models=["claude-opus-5-5"])
    upstream.state.fail = {"claude-opus-5-5": 529}
    r = await gw.post("/v1/messages", json=msg(model="claude-opus-5-5"), headers={"x-api-key": key})
    assert r.status_code == 529  # the provider's error is passed through rather than silently changing model


async def test_breaker_skips_a_failing_model(gw, upstream):
    key = await provision(gw, rpm=100)
    upstream.state.fail = {"claude-opus-5-5": 503}
    for _ in range(3):
        await gw.post("/v1/messages", json=msg(model="claude-opus-5-5"), headers={"x-api-key": key})
    before = len(upstream.state.received)
    await gw.post("/v1/messages", json=msg(model="claude-opus-5-5"), headers={"x-api-key": key})
    assert len(upstream.state.received) == before + 1  # only the fallback was called


async def test_all_upstreams_failing_returns_messages_api_error(gw, upstream):
    key = await provision(gw)
    upstream.state.fail = {"claude-haiku-5-5": 503}
    r = await gw.post("/v1/messages", json=msg(model="claude-haiku-5-5"), headers={"x-api-key": key})
    assert r.status_code == 503 and r.json()["type"] == "error"


async def test_streaming_passthrough_and_usage(gw, upstream):
    key = await provision(gw)
    async with gw.stream("POST", "/v1/messages", json=msg(stream=True), headers={"x-api-key": key}) as r:
        body = b"".join([chunk async for chunk in r.aiter_raw()])
    assert r.status_code == 200 and b"streamed from claude-sonnet-5-5" in body and b"message_stop" in body
    await settle(gw)
    [event] = await ledger(gw, "SELECT stream, output_tokens, input_tokens, cost_usd FROM usage_events")
    assert event["stream"] and event["output_tokens"] == 12 and event["input_tokens"] > 0 and event["cost_usd"] > 0


async def test_unlisted_beta_headers_are_dropped(gw, upstream):
    key = await provision(gw)
    r = await gw.post(
        "/v1/messages",
        json=msg(),
        headers={"x-api-key": key, "anthropic-beta": "prompt-caching-2024-07-31,secret-feature-1"},
    )
    assert upstream.state.headers[0]["anthropic-beta"] == "prompt-caching-2024-07-31"
    assert r.headers["x-switchboard-dropped-betas"] == "secret-feature-1"


async def test_invalid_and_oversized_requests(gw):
    key = await provision(gw)
    assert (await gw.post("/v1/messages", content=b"{not json", headers={"x-api-key": key})).status_code == 400
    gw.app.state.settings.max_body_bytes = 100
    big = msg(text="x" * 500)
    assert (await gw.post("/v1/messages", json=big, headers={"x-api-key": key})).status_code == 413


async def test_policy_change_applies_without_restart(gw):
    key = await provision(gw)
    assert (await gw.post("/v1/messages", json=msg(), headers={"x-api-key": key})).status_code == 200
    r = await gw.put("/admin/apps/support-bot/policy", json={"allowed_models": ["claude-haiku-5-5"]}, headers=ADMIN)
    assert r.status_code == 200
    assert (await gw.post("/v1/messages", json=msg(), headers={"x-api-key": key})).status_code == 403
    rows = await ledger(gw, "SELECT action FROM admin_audit ORDER BY id")
    assert [r["action"] for r in rows][-1] == "set_policy"


async def test_concurrent_requests_record_every_event(gw):
    key = await provision(gw, rpm=1000)
    await asyncio.gather(*(gw.post("/v1/messages", json=msg(), headers={"x-api-key": key}) for _ in range(25)))
    await settle(gw)
    [row] = await ledger(gw, "SELECT requests FROM spend_monthly WHERE scope = 'org'")
    assert row["requests"] == 25


async def test_expired_audit_bodies_are_purged(gw):
    key = await provision(gw, log_bodies=True, retention_days=1)
    await gw.post("/v1/messages", json=msg(), headers={"x-api-key": key})
    await settle(gw)
    async with gw.app.state.pool.connection() as c:
        await c.execute("UPDATE audit_bodies SET expires_at = now() - interval '1 minute'")
    assert (await gw.post("/admin/purge-expired", headers=ADMIN)).json() == {"deleted": 1}


def test_pii_patterns_leave_ids_alone():
    from switchboard.pii import scrub

    assert scrub("order 1234567812345678, sku 4111, ticket 1042")[1] == 0
    assert scrub("4111-1111-1111-1111")[1] == 1
    for phone in ("+1 (303) 555-0142", "303-555-0142", "+44 20 7946 0958"):
        assert scrub(f"call {phone} now")[0] == "call [PHONE] now", phone
    assert scrub("IBAN DE89 3704 0044 0532 0130 00")[1] == 1
    assert json.loads(json.dumps({"ok": True}))
