"""The OpenAI-compatible data plane: other providers get the same keys, limits, budgets, PII policy and metering."""

import json

from tests.conftest import chat, msg, provision
from tests.test_gateway import ledger, settle


async def test_chat_completions_proxy_meters_with_the_provider_key(gw, upstream):
    key = await provision(gw)
    r = await gw.post("/v1/chat/completions", json=chat(), headers={"authorization": f"Bearer {key}"})
    assert r.status_code == 200 and r.json()["choices"][0]["message"]["content"] == "echo from gpt-test"
    assert upstream.state.headers[0]["authorization"] == "Bearer openai-secret"  # app keys never leave the gateway
    await settle(gw)
    [event] = await ledger(gw, "SELECT input_tokens, cache_read_tokens, output_tokens, cost_usd FROM usage_events")
    assert event["cache_read_tokens"] == 100 and event["output_tokens"] == 9 and event["cost_usd"] > 0


async def test_streaming_asks_for_usage_and_meters_it(gw, upstream):
    key = await provision(gw)
    async with gw.stream(
        "POST", "/v1/chat/completions", json=chat(stream=True), headers={"authorization": f"Bearer {key}"}
    ) as r:
        body = b"".join([c async for c in r.aiter_raw()])
    assert r.status_code == 200 and b"streamed from gpt-test" in body and b"[DONE]" in body
    assert json.loads(upstream.state.received[0])["stream_options"] == {"include_usage": True}
    await settle(gw)
    [event] = await ledger(gw, "SELECT stream, output_tokens, cache_read_tokens FROM usage_events")
    assert event["stream"] and event["output_tokens"] == 9 and event["cache_read_tokens"] == 100


async def test_fallback_crosses_providers_and_renames_the_model(gw, upstream):
    key = await provision(gw)
    upstream.state.fail = {"gpt-test": 503}
    r = await gw.post("/v1/chat/completions", json=chat(), headers={"authorization": f"Bearer {key}"})
    assert r.status_code == 200 and r.headers["x-switchboard-model"] == "llama-local"
    second = upstream.state.headers[1]
    assert second["path"] == "/p2/v1/chat/completions" and "authorization" not in second  # keyless local server
    assert json.loads(upstream.state.received[1])["model"] == "meta-llama/Llama-3.3-70B-Instruct"


async def test_each_model_is_served_by_one_api_style(gw):
    key = await provision(gw)
    r = await gw.post(
        "/v1/chat/completions", json=chat(model="claude-sonnet-5-5"), headers={"authorization": f"Bearer {key}"}
    )
    assert r.status_code == 400 and "error" in r.json() and r.json()["error"]["type"] == "invalid_request_error"
    r = await gw.post("/v1/messages", json=msg(model="gpt-test"), headers={"x-api-key": key})
    assert r.status_code == 400 and r.json()["type"] == "error"


async def test_chat_errors_use_the_openai_shape(gw):
    r = await gw.post("/v1/chat/completions", json=chat(), headers={"authorization": "Bearer sbk_bad_key"})
    assert r.status_code == 401 and r.json()["error"]["type"] == "authentication_error"


async def test_pii_redaction_applies_to_chat_messages(gw, upstream):
    key = await provision(gw, pii_mode="redact")
    await gw.post(
        "/v1/chat/completions",
        json=chat(text="mail ada@example.com about order 1042"),
        headers={"authorization": f"Bearer {key}"},
    )
    sent = upstream.state.received[0].decode()
    assert "ada@example.com" not in sent and "1042" in sent


async def test_streamed_aliases_are_billed_under_the_catalog_name(gw, upstream):
    key = await provision(gw)
    upstream.state.fail = {"gpt-test": 503}  # fall back to llama-local, which the provider knows by another name
    async with gw.stream(
        "POST", "/v1/chat/completions", json=chat(stream=True), headers={"authorization": f"Bearer {key}"}
    ) as r:
        b"".join([c async for c in r.aiter_raw()])
    await settle(gw)
    [event] = await ledger(gw, "SELECT served_model FROM usage_events")
    assert event["served_model"] == "llama-local"  # not the provider's meta-llama/... name, which has no price
