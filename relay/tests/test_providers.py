"""Provider neutrality: spec parsing, message translation, and the OpenAI-compatible adapter against a fake stream."""

from types import SimpleNamespace as NS

import openai
from pydantic import BaseModel

from app.llm import OpenAICompatLLM, to_chat_messages, to_chat_tools
from app.pricing import cost_usd
from app.providers import build_model, parse_spec
from app.resilience import RETRYABLE


def test_specs_pick_provider_and_keep_colons_in_model_names():
    assert (parse_spec("openai:gpt-5").provider, parse_spec("openai:gpt-5").model) == ("openai", "gpt-5")
    assert parse_spec("ollama:qwen3:8b").model == "qwen3:8b"
    assert parse_spec("hf:meta-llama/Llama-3.3-70B-Instruct").provider == "huggingface"
    assert parse_spec("claude-haiku-5-5").provider == "anthropic"
    assert (
        parse_spec("qwen3:8b", default_provider="ollama").provider == "ollama"
    )  # unknown prefix is not a provider


def test_build_model_returns_compatible_client_with_preset_url(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    m = build_model("openrouter:qwen/qwen3-235b-a22b")
    assert isinstance(m, OpenAICompatLLM)
    assert str(m.client.base_url).startswith("https://openrouter.ai/api/v1")
    assert build_model("openai:gpt-5").max_tokens_param == "max_completion_tokens"


def test_canonical_messages_translate_to_chat_completions():
    msgs = [
        {"role": "user", "content": "where is order 1042?"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Checking."},
                {"type": "tool_use", "id": "call_1", "name": "get_order", "input": {"order_id": 1042}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_1", "content": "shipped", "is_error": False}
            ],
        },
    ]
    out = to_chat_messages("be brief", msgs)
    assert [m["role"] for m in out] == ["system", "user", "assistant", "tool"]
    assert out[2]["tool_calls"][0]["function"] == {"name": "get_order", "arguments": '{"order_id": 1042}'}
    assert out[3] == {"role": "tool", "tool_call_id": "call_1", "content": "shipped"}
    tools = to_chat_tools([{"name": "get_order", "description": "d", "input_schema": {"type": "object"}}])
    assert tools[0]["function"]["parameters"] == {"type": "object"}


def chunk(content=None, tool=None, finish=None, usage=None):
    tc = None
    if tool:
        i, cid, name, args = tool
        tc = [NS(index=i, id=cid, function=NS(name=name, arguments=args))]
    choices = [] if usage else [NS(delta=NS(content=content, tool_calls=tc), finish_reason=finish)]
    return NS(choices=choices, usage=usage)


class FakeCompletions:
    def __init__(self, chunks=None, message=None):
        self.chunks, self.message, self.calls = chunks or [], message, []

    async def create(self, **params):
        self.calls.append(params)
        if params.get("stream"):

            async def gen():
                for c in self.chunks:
                    yield c

            return gen()
        return NS(choices=[NS(message=NS(content=self.message))])


def fake_llm(**kw):
    comp = FakeCompletions(**kw)
    client = NS(chat=NS(completions=comp))
    return OpenAICompatLLM("m", 256, base_url="http://x/v1", api_key="k", client=client), comp


async def test_streamed_tool_call_split_across_chunks_becomes_one_tool_use_block():
    usage = NS(prompt_tokens=1000, completion_tokens=20, prompt_tokens_details=NS(cached_tokens=800))
    llm, comp = fake_llm(
        chunks=[
            chunk(content="Let me check. "),
            chunk(tool=(0, "call_9", "get_order", '{"order_')),
            chunk(tool=(0, None, None, 'id": 1042}')),
            chunk(finish="tool_calls"),
            chunk(usage=usage),
        ]
    )
    seen = []

    async def on_text(t):
        seen.append(t)

    r = await llm.respond(system="s", tools=[], messages=[{"role": "user", "content": "hi"}], on_text=on_text)
    assert seen == ["Let me check. "]
    assert r.stop_reason == "tool_use"
    assert r.content[1] == {
        "type": "tool_use",
        "id": "call_9",
        "name": "get_order",
        "input": {"order_id": 1042},
    }
    assert (
        r.usage["input_tokens"] == 200 and r.usage["cache_read_input_tokens"] == 800
    )  # same meaning as Anthropic
    assert comp.calls[0]["stream_options"] == {"include_usage": True} and "tools" not in comp.calls[0]


async def test_server_saying_stop_with_tool_calls_still_runs_the_tools():
    llm, _ = fake_llm(chunks=[chunk(tool=(0, "c1", "t", "{}")), chunk(finish="stop")])

    async def on_text(t):
        pass

    r = await llm.respond(system="", tools=[], messages=[{"role": "user", "content": "x"}], on_text=on_text)
    assert r.stop_reason == "tool_use"


class Out(BaseModel):
    intent: str


async def test_parse_validates_json_and_returns_none_on_garbage():
    llm, comp = fake_llm(message='{"intent": "refund"}')
    assert (await llm.parse(system="s", user="u", schema=Out)).intent == "refund"
    assert comp.calls[0]["response_format"]["json_schema"]["name"] == "Out"
    bad, _ = fake_llm(message="sure! here you go")
    assert await bad.parse(system="s", user="u", schema=Out) is None


def test_openai_errors_are_retryable_and_prices_come_from_settings(monkeypatch):
    assert openai.RateLimitError in RETRYABLE and openai.APIConnectionError in RETRYABLE
    from app.config import settings

    monkeypatch.setattr(settings, "prices", {"gpt-5": (1.0, 0.0, 0.1, 10.0)})
    assert cost_usd({"input_tokens": 1_000_000, "output_tokens": 100_000}, "openai:gpt-5") == 2.0
