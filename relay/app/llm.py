"""The model boundary. The agent loop depends on this small interface, so tests can script the model."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

import anthropic

FALLBACK_BETA = "server-side-fallback-2026-07-01"

OnText = Callable[[str], Awaitable[None]]


@dataclass
class LLMResponse:
    content: list[dict]  # API content blocks as plain dicts, ready to store and resend
    stop_reason: str
    usage: dict = field(default_factory=dict)


class LLM(Protocol):
    async def respond(
        self, *, system: str, tools: list[dict], messages: list[dict], on_text: OnText
    ) -> LLMResponse: ...


class AnthropicLLM:
    def __init__(self, model: str, max_tokens: int, refusal_fallback: bool = True):
        self.client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY
        self.model = model
        self.max_tokens = max_tokens
        self.refusal_fallback = refusal_fallback

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
