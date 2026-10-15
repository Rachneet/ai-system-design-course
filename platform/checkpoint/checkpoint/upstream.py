"""Client side: Checkpoint calling an approved MCP server over Streamable HTTP.

Modern servers (2026-07-28) get stateless requests with per-request _meta and mirrored headers. Servers from the
initialize era are detected the way the spec describes (a 400 whose body is not a recognized modern JSON-RPC error)
and then spoken to with initialize and Mcp-Session-Id, re-initializing if the session expires.
"""

import asyncio
import itertools
import json

import httpx

from . import mcp

LEGACY_VERSION = "2025-11-25"
MODERN_CODES = {
    mcp.HEADER_MISMATCH,
    mcp.MISSING_CAPABILITY,
    mcp.UNSUPPORTED_VERSION,
    mcp.INVALID_PARAMS,
    mcp.METHOD_NOT_FOUND,
}
_ids = itertools.count(1)


class UpstreamError(Exception):
    pass


def read_body(resp: httpx.Response, rid) -> dict:
    """Responses may be one JSON object or an SSE stream ending with the response for our id."""
    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                try:
                    msg = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if msg.get("id") == rid and ("result" in msg or "error" in msg):
                    return msg
        raise UpstreamError("SSE stream ended without a response")
    try:
        return resp.json()
    except ValueError:
        raise UpstreamError(f"upstream returned {resp.status_code} without JSON") from None


class Upstream:
    def __init__(self, name: str, url: str, credential: str | None, transport=None, timeout_s: float = 30.0):
        self.name, self.url, self.credential = name, url, credential
        self.client = httpx.AsyncClient(transport=transport, timeout=timeout_s)
        self.legacy: bool | None = None  # unknown until the first exchange
        self.session: str | None = None
        self.ready = False  # legacy handshake done (some servers issue no session id)
        self.lock = asyncio.Lock()

    def _headers(self, extra: dict) -> dict:
        h = {"content-type": "application/json", "accept": "application/json, text/event-stream"} | extra
        if self.credential:
            h["authorization"] = self.credential
        return h

    async def _post(self, body: dict, headers: dict) -> httpx.Response:
        return await self.client.post(self.url, content=json.dumps(body), headers=self._headers(headers))

    async def _initialize(self) -> None:
        rid = next(_ids)
        body = {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "initialize",
            "params": {
                "protocolVersion": LEGACY_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "checkpoint", "version": "0.1.0"},
            },
        }
        resp = await self._post(body, {"mcp-protocol-version": LEGACY_VERSION})
        msg = read_body(resp, rid)
        if "error" in msg:
            raise UpstreamError(f"initialize failed: {msg['error'].get('message')}")
        self.session = resp.headers.get("mcp-session-id")
        self.ready = True
        note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        await self._post(
            note, {"mcp-protocol-version": LEGACY_VERSION} | ({"mcp-session-id": self.session} if self.session else {})
        )

    async def call(
        self, method: str, params: dict, extra_headers: dict | None = None, meta: dict | None = None
    ) -> dict:
        """Returns the JSON-RPC result, or raises UpstreamError with the upstream's error message."""
        extra_headers = extra_headers or {}
        if self.legacy is not True:
            rid = next(_ids)
            body = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params | {"_meta": mcp.request_meta(meta)}}
            headers = {"mcp-protocol-version": mcp.PROTOCOL, "mcp-method": method} | extra_headers
            if "name" in params:
                headers["mcp-name"] = mcp.encode_header(params["name"])
            resp = await self._post(body, headers)
            if resp.status_code == 400:
                try:
                    err = resp.json().get("error") or {}
                except ValueError:
                    err = {}
                if err.get("code") not in MODERN_CODES:
                    self.legacy = True  # an initialize-era server: fall back, per the spec's detection rule
                else:
                    raise UpstreamError(err.get("message", "bad request"))
            if self.legacy is not True:
                self.legacy = False
                return self._unwrap(read_body(resp, rid))
        return await self._legacy_call(method, params, extra_headers, meta)

    async def _legacy_call(self, method, params, extra_headers, meta) -> dict:
        for attempt in range(2):
            async with self.lock:
                if not self.ready:
                    await self._initialize()
            rid = next(_ids)
            body = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params | ({"_meta": meta} if meta else {})}
            headers = {"mcp-protocol-version": LEGACY_VERSION} | extra_headers
            if self.session:
                headers["mcp-session-id"] = self.session
            resp = await self._post(body, headers)
            if resp.status_code == 404 and attempt == 0:
                self.ready, self.session = False, None  # session expired: initialize again once
                continue
            return self._unwrap(read_body(resp, rid))
        raise UpstreamError("upstream session could not be re-established")

    @staticmethod
    def _unwrap(msg: dict) -> dict:
        if "error" in msg:
            raise UpstreamError(msg["error"].get("message", "upstream error"))
        return msg.get("result") or {}

    async def close(self) -> None:
        await self.client.aclose()
