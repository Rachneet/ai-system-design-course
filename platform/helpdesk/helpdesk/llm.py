"""Model calls, always through Switchboard's OpenAI-compatible endpoint with the agent's own Switchboard key. The agent
never holds a provider key and never chooses a provider: Switchboard maps the model name to one, with fallbacks.

Each request carries x-switchboard-tag ticket:<id>:<agent>, so FinOps joins cost to tickets, and a traceparent in
the ticket's trace. A spent budget comes back as 429 with x-should-retry: false; that is not retried, and the caller
degrades (hands the ticket to a person) instead of failing.
"""

import asyncio
import time
from dataclasses import dataclass

import httpx


class ModelError(Exception):
    def __init__(self, message: str, budget: bool = False):
        super().__init__(message)
        self.budget = budget


@dataclass
class Completion:
    message: dict
    usage: dict
    request_id: str
    served_model: str
    latency_ms: int


class Switchboard:
    def __init__(self, base_url: str, transport=None, timeout_s: float = 60.0, retries: int = 2):
        self.client = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=timeout_s)
        self.retries = retries

    async def chat(
        self, key: str, model: str, messages: list, tools: list, tag: str, traceparent: str, max_tokens: int
    ) -> Completion:
        body = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if tools:
            body["tools"] = tools
        headers = {"authorization": f"Bearer {key}", "x-switchboard-tag": tag, "traceparent": traceparent}
        last = "no attempt"
        for attempt in range(self.retries + 1):
            started = time.perf_counter()
            try:
                resp = await self.client.post("/v1/chat/completions", json=body, headers=headers)
            except httpx.TransportError as e:
                last = f"{type(e).__name__} reaching Switchboard"
            else:
                if resp.status_code == 200:
                    data = resp.json()
                    return Completion(
                        data["choices"][0]["message"],
                        data.get("usage") or {},
                        resp.headers.get("x-request-id", ""),
                        resp.headers.get("x-switchboard-model", model),
                        int((time.perf_counter() - started) * 1000),
                    )
                last = f"Switchboard answered {resp.status_code}: {resp.text[:200]}"
                if resp.headers.get("x-should-retry") == "false":
                    raise ModelError(last, budget="budget" in resp.headers.get("x-switchboard-limit", ""))
                if resp.status_code < 500 and resp.status_code != 429:
                    raise ModelError(last)
            if attempt < self.retries:
                await asyncio.sleep(0.2 * 2**attempt)
        raise ModelError(last)

    async def close(self) -> None:
        await self.client.aclose()
