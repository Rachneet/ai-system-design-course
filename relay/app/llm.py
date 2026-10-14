"""The model boundary. The agent loop depends on this small interface, so tests can script the model and any
provider can sit behind it.

Messages use one canonical shape everywhere (stored sessions, evals, judges): content blocks of type text, tool_use
and tool_result. AnthropicLLM sends it as is; OpenAICompatLLM translates it to and from Chat Completions, which
OpenAI, Gemini, OpenRouter, Hugging Face, vLLM, Ollama and most gateways speak. Pick one with a spec string
(see providers.py).
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

import anthropic
import openai
from pydantic import BaseModel, ValidationError

FALLBACK_BETA = "server-side-fallback-2026-07-01"

OnText = Callable[[str], Awaitable[None]]


@dataclass
class LLMResponse:
    content: list[dict]  # API content blocks as plain dicts, ready to store and resend
    stop_reason: str
    usage: dict = field(default_factory=dict)


T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    async def respond(
        self, *, system: str, tools: list[dict], messages: list[dict], on_text: OnText
    ) -> LLMResponse: ...


class StructuredLLM(Protocol):
    """What the narrow calls need: routers, judges, quarantine, memory extraction and the user simulator."""

    model: str

    async def parse(self, *, system: str, user: str, schema: type[T], max_tokens: int = 1024) -> T | None: ...
    async def complete(self, *, system: str, messages: list[dict], max_tokens: int = 512) -> str: ...


class AnthropicLLM:
    def __init__(self, model: str, max_tokens: int, refusal_fallback: bool = True, max_retries: int = 2):
        # ResilientLLM passes max_retries=0 and retries itself, so SDK and app retries never multiply.
        self.client = anthropic.AsyncAnthropic(max_retries=max_retries)  # reads ANTHROPIC_API_KEY
        self.model = model
        self.provider = "anthropic"
        self.max_tokens = max_tokens
        # Server-side refusal fallback exists for Opus and Sonnet tiers, not Haiku.
        self.refusal_fallback = refusal_fallback and "haiku" not in model

    async def respond(self, *, system, tools, messages, on_text) -> LLMResponse:
        params = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "tools": tools,
            "messages": messages,
            "cache_control": {"type": "ephemeral"},  # cache the growing prefix on every loop step
        }
        if self.refusal_fallback:
            # If the model declines, the API re-runs the request on a recommended fallback model.
            stream = self.client.beta.messages.stream(**params, betas=[FALLBACK_BETA], fallbacks="default")
        else:
            stream = self.client.messages.stream(**params)
        async with stream as s:
            async for text in s.text_stream:
                await on_text(text)
            msg = await s.get_final_message()
        u = msg.usage
        return LLMResponse(
            content=[b.model_dump(mode="json", exclude_none=True) for b in msg.content],
            stop_reason=msg.stop_reason,
            usage={
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "cache_read_input_tokens": u.cache_read_input_tokens or 0,
                "cache_creation_input_tokens": u.cache_creation_input_tokens or 0,
            },
        )

    async def parse(self, *, system, user, schema, max_tokens=1024):
        resp = await self.client.messages.parse(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
        return resp.parsed_output

    async def complete(self, *, system, messages, max_tokens=512) -> str:
        resp = await self.client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system, messages=messages
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()


FINISH = {"stop": "end_turn", "tool_calls": "tool_use", "function_call": "tool_use", "length": "max_tokens"}


def _flat(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if b.get("type") == "text")


def to_chat_messages(system: str, messages: list[dict]) -> list[dict]:
    """Canonical blocks to Chat Completions messages. Tool results become role "tool" messages, placed straight
    after the assistant message that called them, as the protocol requires."""
    out = [{"role": "system", "content": system}] if system else []
    for m in messages:
        blocks = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
        if m["role"] == "assistant":
            msg: dict = {"role": "assistant", "content": _flat(blocks) or None}
            calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {})},
                }
                for b in blocks
                if b.get("type") == "tool_use"
            ]
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
            continue
        for b in blocks:
            if b.get("type") == "tool_result":
                text = _flat(b.get("content") or "")
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": b["tool_use_id"],
                        "content": ("ERROR: " if b.get("is_error") else "") + text,
                    }
                )
        text = _flat(blocks)
        if text:
            out.append({"role": "user", "content": text})
    return out


def to_chat_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


class OpenAICompatLLM:
    """Any OpenAI-compatible Chat Completions endpoint. Prompt caching is automatic on providers that support it
    (OpenAI, Gemini implicit caching); there is nothing to mark, so keep the prefix stable."""

    def __init__(
        self,
        model: str,
        max_tokens: int,
        *,
        base_url: str,
        api_key: str,
        provider: str = "compatible",
        max_tokens_param: str = "max_tokens",
        max_retries: int = 2,
        client=None,
    ):
        self.client = client or openai.AsyncOpenAI(
            base_url=base_url, api_key=api_key, max_retries=max_retries
        )
        self.model, self.max_tokens, self.provider = model, max_tokens, provider
        self.max_tokens_param = max_tokens_param

    def _limit(self, n: int) -> dict:
        return {self.max_tokens_param: n}

    async def respond(self, *, system, tools, messages, on_text) -> LLMResponse:
        params = {
            "model": self.model,
            "messages": to_chat_messages(system, messages),
            "stream": True,
            "stream_options": {"include_usage": True},
            **self._limit(self.max_tokens),
        }
        if tools:
            params["tools"] = to_chat_tools(tools)
        text, calls, finish, usage = [], {}, None, None
        stream = await self.client.chat.completions.create(**params)
        async for chunk in stream:
            usage = chunk.usage or usage
            for choice in chunk.choices:
                d = choice.delta
                if d and d.content:
                    text.append(d.content)
                    await on_text(d.content)
                for tc in (d.tool_calls or []) if d else []:
                    slot = calls.setdefault(tc.index, {"id": None, "name": "", "args": []})
                    slot["id"] = tc.id or slot["id"]
                    if tc.function and tc.function.name:
                        slot["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["args"].append(tc.function.arguments)
                finish = choice.finish_reason or finish
        content = [{"type": "text", "text": "".join(text)}] if text else []
        for i, c in sorted(calls.items()):
            raw = "".join(c["args"]) or "{}"
            try:
                args = json.loads(raw)
            except json.JSONDecodeError:
                args = {"_unparsed_arguments": raw}  # the tool layer rejects it, and the model sees the error
            content.append(
                {"type": "tool_use", "id": c["id"] or f"call_{i}", "name": c["name"], "input": args}
            )
        stop = FINISH.get(finish or "stop", finish or "end_turn")
        if calls and stop == "end_turn":
            stop = "tool_use"  # some servers report "stop" even when they returned tool calls
        cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        return LLMResponse(
            content=content,
            stop_reason=stop,
            usage={
                "input_tokens": prompt - cached,  # same meaning as Anthropic's: uncached input only
                "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
                "cache_read_input_tokens": cached,
                "cache_creation_input_tokens": 0,
            },
        )

    async def parse(self, *, system, user, schema, max_tokens=1024):
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=to_chat_messages(system, [{"role": "user", "content": user}]),
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
            },
            **self._limit(max_tokens),
        )
        raw = resp.choices[0].message.content or ""
        try:
            return schema.model_validate_json(raw)
        except ValidationError:
            return None  # callers fall back to a safe default, exactly as with a refusal

    async def complete(self, *, system, messages, max_tokens=512) -> str:
        resp = await self.client.chat.completions.create(
            model=self.model, messages=to_chat_messages(system, messages), **self._limit(max_tokens)
        )
        return (resp.choices[0].message.content or "").strip()


class EchoLLM:
    """Offline stand-in for container smoke tests: repeats the last user message. Not for evaluating behaviour."""

    async def respond(self, *, system, tools, messages, on_text) -> LLMResponse:
        content = messages[-1]["content"]
        last = (
            content
            if isinstance(content, str)
            else " ".join(b.get("text", "") for b in content if b.get("type") == "text")
        )
        reply = f"(echo) {last}"
        await on_text(reply)
        return LLMResponse(
            [{"type": "text", "text": reply}],
            "end_turn",
            {"input_tokens": len(last) // 4, "output_tokens": 10},
        )
