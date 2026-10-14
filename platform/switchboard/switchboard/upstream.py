"""The provider side: an HTTP client to the Anthropic Messages API, a streaming usage parser, and breakers."""

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
