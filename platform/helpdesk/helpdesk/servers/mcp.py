"""A small MCP 2026-07-28 server (stateless Streamable HTTP, tools only) for Helpdesk's systems of record.

Each server trusts one caller: Checkpoint. A tools/call must carry Checkpoint's signed assertion
(x-checkpoint-assertion, RS256, verified against Checkpoint's JWKS) with this server as audience and the called tool
in its `tool` claim. The user (sub), the agent (act.sub) and the tenant come from the assertion, never from the
arguments, so a model cannot claim to be someone else. tools/list is not secret and needs no assertion.
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx
import jwt
from fastapi import Request
from fastapi.responses import JSONResponse, Response

PROTOCOL = "2026-07-28"
META = "io.modelcontextprotocol/"
TYPES = {"string": str, "integer": int, "boolean": bool, "object": dict, "array": list}


@dataclass(frozen=True)
class Caller:
    user: str
    agent: str
    tenant: str
    approval: int | None = None  # set when a person approved exactly this call in Checkpoint


class ToolError(Exception):
    """A failure the model should read and act on (not found, not allowed, invalid state)."""


@dataclass
class Tool:
    name: str
    description: str
    properties: dict
    fn: Callable[..., Awaitable[dict]]
    required: list[str] = field(default_factory=list)
    read_only: bool = True

    def descriptor(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.properties,
                "required": self.required,
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": self.read_only, "destructiveHint": False, "openWorldHint": False},
        }

    def check(self, args: dict) -> None:
        for key in self.required:
            if key not in args:
                raise ToolError(f"missing argument {key}")
        for key, value in args.items():
            prop = self.properties.get(key)
            if prop is None:
                raise ToolError(f"unknown argument {key}")
            want = TYPES.get(prop.get("type", ""), object)
            if not isinstance(value, want) or (want is int and isinstance(value, bool)):
                raise ToolError(f"{key} must be a {prop.get('type')}")
            if "enum" in prop and value not in prop["enum"]:
                raise ToolError(f"{key} must be one of {', '.join(map(str, prop['enum']))}")


class AssertionVerifier:
    """Fetches Checkpoint's public keys once, again on an unknown key id (rotation), and verifies assertions."""

    def __init__(self, jwks_url: str, transport=None, issuer: str = "checkpoint"):
        self.jwks_url, self.issuer = jwks_url, issuer
        self.client = httpx.AsyncClient(transport=transport, timeout=10)
        self.keys: dict[str, object] = {}
        self.fetched_at: float | None = None  # monotonic time counts from boot
        self.lock = asyncio.Lock()

    async def _fetch(self) -> None:
        async with self.lock:
            if (
                self.fetched_at is not None and time.monotonic() - self.fetched_at < 5
            ):  # at most one refetch per 5 s, however many bad kids arrive
                return
            resp = await self.client.get(self.jwks_url)
            resp.raise_for_status()
            jwks = jwt.PyJWKSet.from_dict(resp.json())
            self.keys = {k.key_id: k.key for k in jwks.keys}
            self.fetched_at = time.monotonic()

    async def verify(self, token: str, audience: str, tool: str) -> Caller:
        kid = jwt.get_unverified_header(token).get("kid")
        if kid not in self.keys:
            await self._fetch()
        if kid not in self.keys:
            raise jwt.InvalidKeyError("unknown signing key")
        claims = jwt.decode(
            token,
            self.keys[kid],
            algorithms=["RS256"],
            audience=audience,
            issuer=self.issuer,
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
        if claims.get("tool") != tool:
            raise jwt.InvalidTokenError("assertion is for a different tool")
        actor = str((claims.get("act") or {}).get("sub", ""))
        return Caller(str(claims["sub"]), actor, str(claims.get("tenant", "")), claims.get("approval"))

    async def close(self) -> None:
        await self.client.aclose()


def rpc_error(rid, code: int, message: str, status: int = 400) -> JSONResponse:
    body = {"jsonrpc": "2.0", "error": {"code": code, "message": message}} | ({"id": rid} if rid is not None else {})
    return JSONResponse(body, status_code=status)


def result(rid, payload: dict) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": rid, "result": {"resultType": "complete"} | payload})


class Server:
    def __init__(self, name: str, tools: list[Tool], tenants: tuple[str, ...]):
        self.name, self.tenants = name, tenants
        self.tools = {t.name: t for t in tools}

    async def handle(self, request: Request, verifier: AssertionVerifier) -> Response:
        try:
            body = json.loads(await request.body())
        except ValueError:
            return rpc_error(None, -32700, "Parse error")
        if not isinstance(body, dict) or "id" not in body:
            return Response(status_code=202)
        rid, method = body.get("id"), body.get("method")
        params = body.get("params") or {}
        version = (params.get("_meta") or {}).get(META + "protocolVersion")
        if request.headers.get("mcp-protocol-version") != PROTOCOL or version != PROTOCOL:
            return rpc_error(rid, -32022, f"Unsupported protocol version; this server speaks {PROTOCOL}")
        if request.headers.get("mcp-method") != method:
            return rpc_error(rid, -32020, "Header mismatch: mcp-method")
        if method == "ping":
            return result(rid, {})
        if method == "tools/list":
            return result(rid, {"tools": [t.descriptor() for t in self.tools.values()]})
        if method != "tools/call":
            return rpc_error(rid, -32601, f"Method not found: {method}", 404)

        name, args = params.get("name", ""), params.get("arguments") or {}
        tool = self.tools.get(name)
        if tool is None:
            return rpc_error(rid, -32602, f"Unknown tool: {name}", 200)
        try:
            caller = await verifier.verify(request.headers.get("x-checkpoint-assertion", ""), self.name, name)
        except (jwt.PyJWTError, httpx.HTTPError) as e:
            return rpc_error(rid, -32001, f"Checkpoint assertion required: {e}", 401)
        try:
            if caller.tenant not in self.tenants:
                raise ToolError("not found")  # this system does not serve that tenant; say nothing more
            tool.check(args)
            out = await tool.fn(caller, **args)
        except ToolError as e:
            return result(rid, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        return result(rid, {"content": [{"type": "text", "text": json.dumps(out)}], "structuredContent": out})
