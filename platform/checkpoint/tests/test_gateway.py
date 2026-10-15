"""Checkpoint end to end: transport rules, identity, Atlas catalog, Cedar policy, approvals, upstream protocols,
assertions and output scanning."""

import jwt

from tests import mock_servers
from tests.conftest import ADMIN, Gateway, agent, call, rpc, settings, user_token


async def tools(client, auth, user=None):
    body, headers = rpc("tools/list")
    r = await client.post("/mcp", json=body, headers=headers | auth | ({"x-user-token": user} if user else {}))
    assert r.status_code == 200, r.text
    return sorted(t["name"] for t in r.json()["result"]["tools"])


async def test_agents_see_only_tools_policy_lets_them_see(gw):
    refunds, other = await agent(gw, "refunds"), await agent(gw, "concierge")
    assert await tools(gw, refunds) == ["payments__refund", "weather__get_forecast"]
    assert await tools(gw, other) == ["weather__get_forecast"]  # and the plain-HTTP server never appears


async def test_transport_rules_are_enforced(gw):
    a = await agent(gw)
    body, headers = rpc("tools/call", {"name": "weather__get_forecast", "arguments": {"city": "Oslo"}})
    bad = await gw.post("/mcp", json=body, headers=headers | a | {"mcp-name": "payments__refund"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == -32020  # routing header lies about the body
    body, headers = rpc("tools/list")
    body["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] = "2024-01-01"
    old = await gw.post("/mcp", json=body, headers=headers | a | {"mcp-protocol-version": "2024-01-01"})
    assert old.status_code == 400 and old.json()["error"]["data"]["supported"] == ["2026-07-28"]
    body, headers = rpc("tools/list")
    del body["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"]
    assert (await gw.post("/mcp", json=body, headers=headers | a)).json()["error"]["code"] == -32602
    body, headers = rpc("resources/subscribe")
    assert (await gw.post("/mcp", json=body, headers=headers | a)).status_code == 404
    assert (await gw.get("/mcp", headers=a)).status_code == 405
    assert (await gw.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/x"}, headers=a)).status_code == 202
    body, headers = rpc("tools/list")
    assert (
        await gw.post("/mcp", json=body, headers=headers | a | {"origin": "https://evil.example"})
    ).status_code == 403
    assert (await gw.post("/mcp", json=body, headers=headers)).status_code == 401


async def test_allowed_call_reaches_a_legacy_server_with_a_verifiable_assertion(gw):
    a = await agent(gw)
    r = await call(gw, a, "payments__refund", {"amount": 50, "customer_id": "c42"}, user_token("u1"))
    assert r.json()["result"]["content"][0]["text"] == "Refunded 50" and not r.json()["result"].get("isError")
    await call(gw, a, "payments__refund", {"amount": 20, "customer_id": "c42"}, user_token("u1"))
    assert mock_servers.state["initializes"] == 1  # one handshake, then the session is reused
    sent = next(
        s for s in mock_servers.seen if s["host"] == "payments.example" and s["body"].get("method") == "tools/call"
    )
    assert sent["headers"]["authorization"] == "Bearer payments-service-credential"  # never the agent's token
    jwks = (await gw.get("/.well-known/jwks.json")).json()
    key = jwt.PyJWK(jwks["keys"][0]).key
    claims = jwt.decode(
        sent["headers"]["x-checkpoint-assertion"], key, algorithms=["RS256"], audience="com.acme/payments"
    )
    assert (claims["sub"], claims["act"], claims["tool"]) == ("u1", {"sub": "refunds"}, "refund")


async def test_policy_denies_with_reasons(gw):
    a = await agent(gw)
    sales = await call(gw, a, "payments__refund", {"amount": 50, "customer_id": "c1"}, user_token("u2", ("sales",)))
    assert sales.json()["result"]["isError"] and "no policy permits" in sales.json()["result"]["content"][0]["text"]
    own = await call(gw, a, "payments__refund", {"amount": 50, "customer_id": "u1"}, user_token("u1"))
    assert "no-self-refund" in own.json()["result"]["content"][0]["text"]
    other = await agent(gw, "concierge")
    hidden = await call(gw, other, "payments__refund", {"amount": 5, "customer_id": "c1"}, user_token("u1"))
    assert hidden.json()["result"]["isError"]
    assert not any(s["body"].get("method") == "tools/call" for s in mock_servers.seen)  # nothing reached upstream


async def test_large_refunds_wait_for_a_person_and_approvals_are_single_use(gw):
    a = await agent(gw)
    approver = await agent(gw, "finance-lead", role="approver")
    args, user = {"amount": 900, "customer_id": "c7"}, user_token("u1")
    held = (await call(gw, a, "payments__refund", args, user)).json()["result"]
    approval_id = held["structuredContent"]["approvalId"]
    assert held["isError"] and held["structuredContent"]["status"] == "pending"
    assert (
        await gw.post(f"/approvals/{approval_id}/decision", json={"decision": "approve"}, headers=a)
    ).status_code == 401
    pending = (await gw.get("/approvals", headers=approver)).json()["approvals"]
    assert [p["id"] for p in pending] == [approval_id] and pending[0]["args"] == args
    assert (
        await gw.post(f"/approvals/{approval_id}/decision", json={"decision": "approve"}, headers=approver)
    ).status_code == 200
    changed = await call(
        gw, a, "payments__refund", args | {"amount": 1900}, user, {"io.checkpoint/approvalId": approval_id}
    )
    assert changed.json()["result"]["isError"]  # approval covers exactly the approved arguments
    done = await call(gw, a, "payments__refund", args, user, {"io.checkpoint/approvalId": approval_id})
    assert done.json()["result"]["content"][0]["text"] == "Refunded 900"
    again = await call(gw, a, "payments__refund", args, user, {"io.checkpoint/approvalId": approval_id})
    assert again.json()["result"]["isError"]  # used once; a second refund needs a new approval


async def test_tool_output_is_scanned_and_param_headers_flow_both_ways(gw):
    a = await agent(gw)
    missing = await call(gw, a, "weather__get_forecast", {"city": "evil"})
    assert missing.status_code == 400 and missing.json()["error"]["code"] == -32020  # Mcp-Param-City required
    r = await call(gw, a, "weather__get_forecast", {"city": "evil"}, extra_headers={"mcp-param-city": "evil"})
    result = r.json()["result"]
    text = result["content"][0]["text"]
    assert "\u200b" not in text and "AKIAIOSFODNN7EXAMPLE" not in text and text.startswith("[checkpoint:")
    assert result["_meta"]["io.checkpoint/flags"] == [
        "hidden_unicode_removed",
        "instruction_like_text",
        "secret_redacted",
    ]
    sent = next(s for s in mock_servers.seen if s["host"] == "weather.example" and s["body"]["method"] == "tools/call")
    assert sent["headers"]["mcp-param-city"] == "evil" and sent["headers"]["mcp-name"] == "get_forecast"


async def test_rate_limits_and_bad_user_tokens(pg_uri, schema):
    async with Gateway(settings(pg_uri, schema, calls_per_minute=2)) as gw:
        a = await agent(gw)
        h = {"mcp-param-city": "Oslo"}
        for _ in range(2):
            assert (
                not (await call(gw, a, "weather__get_forecast", {"city": "Oslo"}, extra_headers=h))
                .json()["result"]
                .get("isError")
            )
        third = await call(gw, a, "weather__get_forecast", {"city": "Oslo"}, extra_headers=h)
        assert "Rate limit" in third.json()["result"]["content"][0]["text"]
        forged = await call(
            gw,
            a,
            "payments__refund",
            {"amount": 5, "customer_id": "c"},
            user_token(secret="not-the-secret-0123456789abcdefghij"),
        )
        assert forged.status_code == 401


async def test_decisions_are_logged_and_bad_policies_never_load(gw, tmp_path):
    a = await agent(gw)
    await call(gw, a, "payments__refund", {"amount": 50, "customer_id": "c1"}, user_token("u1"))
    await call(gw, a, "payments__refund", {"amount": 50, "customer_id": "u1"}, user_token("u1"))
    log = (await gw.get("/admin/decisions", headers=ADMIN)).json()["decisions"]
    assert [(d["decision"], d["policies"]) for d in log] == [("deny", ["no-self-refund"]), ("allow", ["refunds-small"])]
    gw.app.state.settings.policy_file = str(tmp_path / "broken.cedar")
    (tmp_path / "broken.cedar").write_text("permit(principal,")
    assert (await gw.post("/admin/policy/reload", headers=ADMIN)).status_code == 422
    assert (await call(gw, a, "payments__refund", {"amount": 50, "customer_id": "c1"}, user_token("u1"))).json()[
        "result"
    ].get("isError") is not True
