"""The provider side: HTTP clients for the Anthropic Messages API and any OpenAI-compatible Chat Completions
endpoint, streaming usage parsers for both, and breakers."""

import json
import time

import httpx

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 529}


class Breaker:
    def __init__(self, threshold: int, reset_s: float, clock=time.monotonic):
        self.threshold, self.reset_s, self.clock = threshold, reset_s, clock
        self.failures, self.opened_at = 0, None

    def allow(self) -> bool:
        return self.opened_at is None or self.clock() - self.opened_at >= self.reset_s

    def success(self) -> None:
        self.failures, self.opened_at = 0, None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold or self.opened_at is not None:
            self.opened_at = self.clock()


class UsageParser:
    """Reads usage from a Messages API SSE stream without altering the bytes passed to the client."""

    def __init__(self):
        self.buf = b""
        self.usage: dict = {}
        self.model: str | None = None
        self.error_type: str | None = None

    def feed(self, chunk: bytes) -> None:
        self.buf += chunk
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            if not line.startswith(b"data:"):
                continue
            try:
                event = json.loads(line[5:].strip())
            except ValueError:
                continue
            kind = event.get("type")
            if kind == "message_start":
                msg = event.get("message", {})
                self.model = msg.get("model")
                self.usage.update({k: v for k, v in (msg.get("usage") or {}).items() if isinstance(v, int)})
            elif kind == "message_delta":
                self.usage.update({k: v for k, v in (event.get("usage") or {}).items() if isinstance(v, int)})
            elif kind == "error":
                self.error_type = (event.get("error") or {}).get("type", "error")


def chat_usage(u: dict | None) -> dict:
    """Chat Completions usage in the gateway's canonical shape. Cached tokens are counted once, as cache reads."""
    if not u:
        return {}
    cached = ((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0
    return {
        "input_tokens": max(0, (u.get("prompt_tokens") or 0) - cached),
        "output_tokens": u.get("completion_tokens") or 0,
        "cache_read_input_tokens": cached,
        "cache_creation_input_tokens": 0,
    }


class ChatUsageParser(UsageParser):
    """Reads usage from a Chat Completions SSE stream (the final chunk carries it when include_usage is set)."""

    def feed(self, chunk: bytes) -> None:
        self.buf += chunk
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            if not line.startswith(b"data:") or line[5:].strip() == b"[DONE]":
                continue
            try:
                event = json.loads(line[5:].strip())
            except ValueError:
                continue
            self.model = event.get("model") or self.model
            if event.get("usage"):
                self.usage = chat_usage(event["usage"])
            if event.get("error"):
                self.error_type = (event["error"] or {}).get("type") or "error"


class ChatUpstream:
    """One OpenAI-compatible provider. base_url ends in /v1 (or the provider's equivalent)."""

    def __init__(self, base_url: str, api_key: str, connect_s: float, read_s: float, transport=None):
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            transport=transport,
            timeout=httpx.Timeout(connect=connect_s, read=read_s, write=30.0, pool=5.0),
            limits=httpx.Limits(max_connections=500, max_keepalive_connections=100),
        )

    async def send(self, body: bytes) -> httpx.Response:
        headers = {"content-type": "application/json"}
        if self.api_key:  # local servers (Ollama, vLLM without --api-key) need none
            headers["authorization"] = f"Bearer {self.api_key}"
        request = self.client.build_request("POST", "chat/completions", content=body, headers=headers)
        return await self.client.send(request, stream=True)

    async def close(self) -> None:
        await self.client.aclose()


class Upstream:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        connect_s: float,
        read_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            base_url=base_url,
            transport=transport,
            timeout=httpx.Timeout(connect=connect_s, read=read_s, write=30.0, pool=5.0),
            limits=httpx.Limits(max_connections=500, max_keepalive_connections=100),
        )

    async def send(self, body: bytes, version: str, betas: list[str]) -> httpx.Response:
        headers = {"x-api-key": self.api_key, "anthropic-version": version, "content-type": "application/json"}
        if betas:
            headers["anthropic-beta"] = ",".join(betas)
        request = self.client.build_request("POST", "/v1/messages", content=body, headers=headers)
        return await self.client.send(request, stream=True)

    async def close(self) -> None:
        await self.client.aclose()
