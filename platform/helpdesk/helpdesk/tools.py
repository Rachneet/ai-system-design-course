"""Tool calls, always through Checkpoint's one MCP endpoint (protocol 2026-07-28) with the agent's own token and the
signed-in user's JWT. The agent never holds a tool credential: Checkpoint calls the system with its own assertion.

Checkpoint answers policy outcomes as tool results, so the model can read them. This client also classifies them,
so the runtime can act on them: ok, denied, held (waiting for a person, with the approval id), or error.
"""

import base64
import itertools
import re
from dataclasses import dataclass, field

import httpx

PROTOCOL = "2026-07-28"
META = "io.modelcontextprotocol/"
APPROVAL_KEY = "io.checkpoint/approvalId"
SAFE = re.compile(r"^[\x21-\x7e]([\x20-\x7e]*[\x21-\x7e])?$")
_ids = itertools.count(1)


@dataclass
class ToolResult:
    outcome: str  # ok | denied | held | error | refused
    text: str
    structured: dict = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    @property
    def approval_id(self) -> int | None:
        return self.structured.get("approvalId") if self.outcome == "held" else None


def header_value(value) -> str:
    text = "true" if value is True else "false" if value is False else str(value)
    if SAFE.match(text) and not (text.startswith("=?base64?") and text.endswith("?=")):
        return text
    return "=?base64?" + base64.b64encode(text.encode()).decode() + "?="


def param_headers(schema: dict | None, args: dict) -> dict:
    """MCP 2026-07-28: properties marked x-mcp-header are mirrored into Mcp-Param-<name> headers."""
    out = {}

    def walk(node: dict, value: dict) -> None:
        for key, prop in (node.get("properties") or {}).items():
            if not isinstance(prop, dict) or not isinstance(value, dict) or key not in value:
                continue
            if isinstance(prop.get("x-mcp-header"), str):
                out[f"Mcp-Param-{prop['x-mcp-header']}"] = header_value(value[key])
            walk(prop, value[key])

    walk(schema or {}, args)
    return out


class Checkpoint:
    def __init__(self, base_url: str, transport=None, timeout_s: float = 30.0):
        self.client = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=timeout_s)

    async def _rpc(self, token: str, user_token: str | None, method: str, params: dict, extra: dict | None = None):
        meta = {META + "protocolVersion": PROTOCOL, META + "clientCapabilities": {}} | params.pop("_meta", {})
        body = {"jsonrpc": "2.0", "id": next(_ids), "method": method, "params": params | {"_meta": meta}}
        headers = {"authorization": f"Bearer {token}", "mcp-protocol-version": PROTOCOL, "mcp-method": method}
        if "name" in params:
            headers["mcp-name"] = header_value(params["name"])
        if user_token:
            headers["x-user-token"] = user_token
        return await self.client.post("/mcp", json=body, headers=headers | (extra or {}))

    async def list_tools(self, token: str, user_token: str | None) -> list[dict]:
        resp = await self._rpc(token, user_token, "tools/list", {})
        resp.raise_for_status()
        return resp.json()["result"]["tools"]

    async def call(
        self,
        token: str,
        user_token: str | None,
        tool: dict,
        args: dict,
        approval_id: int | None = None,
        traceparent: str | None = None,
    ) -> ToolResult:
        meta = ({APPROVAL_KEY: approval_id} if approval_id is not None else {}) | (
            {"traceparent": traceparent} if traceparent else {}
        )
        params = {"name": tool["name"], "arguments": args, "_meta": meta}
        try:
            resp = await self._rpc(
                token, user_token, "tools/call", params, param_headers(tool.get("inputSchema"), args)
            )
        except httpx.TransportError as e:
            return ToolResult("error", f"Checkpoint could not be reached ({type(e).__name__}).")
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if "error" in data or resp.status_code >= 400:
            message = (data.get("error") or {}).get("message") or f"Checkpoint answered {resp.status_code}"
            return ToolResult("refused" if resp.status_code in (401, 403) else "error", message)
        result = data["result"]
        text = "\n".join(b.get("text", "") for b in result.get("content") or [] if b.get("type") == "text")
        structured = result.get("structuredContent") or {}
        flags = (result.get("_meta") or {}).get("io.checkpoint/flags", [])
        if not result.get("isError"):
            return ToolResult("ok", text, structured, flags)
        if "approvalId" in structured:
            return ToolResult("held", text, structured, flags)
        return ToolResult("denied" if text.startswith("Denied") else "error", text, structured, flags)

    async def close(self) -> None:
        await self.client.aclose()
