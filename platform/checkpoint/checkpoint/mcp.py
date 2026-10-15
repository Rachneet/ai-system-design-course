"""MCP 2026-07-28 Streamable HTTP rules that a gateway must enforce.

Every request carries its protocol version and client capabilities in params._meta, mirrored into headers
(MCP-Protocol-Version, Mcp-Method, Mcp-Name, Mcp-Param-*). A gateway routes and authorizes on what it sees, so a
header that disagrees with the body is an attack surface: it is rejected with 400 and HeaderMismatch (-32020).
"""

import base64
import re

PROTOCOL = "2026-07-28"
SUPPORTED = [PROTOCOL]
META = "io.modelcontextprotocol/"

PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602
HEADER_MISMATCH, MISSING_CAPABILITY, UNSUPPORTED_VERSION = -32020, -32021, -32022
TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")  # RFC 9110 tchar
SAFE_VALUE = re.compile(r"^[\x21-\x7e]([\x20-\x7e]*[\x21-\x7e])?$")


class ProtocolError(Exception):
    def __init__(self, status: int, code: int, message: str, data=None, rid=None):
        super().__init__(message)
        self.status, self.code, self.message, self.data, self.id = status, code, message, data, rid

    def body(self) -> dict:
        err = {"code": self.code, "message": self.message} | ({"data": self.data} if self.data is not None else {})
        return {"jsonrpc": "2.0", "error": err} | ({"id": self.id} if self.id is not None else {})


def encode_header(value) -> str:
    """Value Encoding: booleans and integers as text; anything not plain visible ASCII as =?base64?...?=."""
    text = "true" if value is True else "false" if value is False else str(value)
    if SAFE_VALUE.match(text) and not (text.startswith("=?base64?") and text.endswith("?=")):
        return text
    return "=?base64?" + base64.b64encode(text.encode()).decode() + "?="


def decode_header(value: str) -> str:
    if value.startswith("=?base64?") and value.endswith("?="):
        return base64.b64decode(value[9:-2]).decode()
    return value


def header_params(schema: dict | None) -> dict[str, list[str]]:
    """x-mcp-header annotations: header name -> property path. Only chains of `properties` keys count."""
    found: dict[str, list[str]] = {}

    def walk(node: dict, path: list[str]) -> None:
        for key, prop in (node.get("properties") or {}).items():
            if not isinstance(prop, dict):
                continue
            name = prop.get("x-mcp-header")
            if isinstance(name, str) and TOKEN.match(name) and prop.get("type") in ("string", "integer", "boolean"):
                found[name.lower()] = path + [key]
            walk(prop, path + [key])

    walk(schema or {}, [])
    return found


def value_at(args: dict, path: list[str]):
    cur = args
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def param_headers(schema: dict | None, args: dict) -> dict[str, str]:
    """Headers a client MUST send for a tools/call whose tool schema marks parameters with x-mcp-header."""
    out = {}
    for name, path in header_params(schema).items():
        v = value_at(args, path)
        if v is not None:
            out[f"Mcp-Param-{name}"] = encode_header(v)
    return out


def validate(headers, body) -> dict:
    """Check one incoming JSON-RPC request against the transport rules. Returns params on success."""
    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0" or not isinstance(body.get("method"), str):
        raise ProtocolError(400, INVALID_REQUEST, "Body must be one JSON-RPC 2.0 request")
    rid, method = body.get("id"), body["method"]
    params = body.get("params") or {}
    meta = params.get("_meta") or {}
    version = meta.get(META + "protocolVersion")
    if version is None or not isinstance(meta.get(META + "clientCapabilities"), dict):
        raise ProtocolError(400, INVALID_PARAMS, "_meta must carry protocolVersion and clientCapabilities", rid=rid)
    if version not in SUPPORTED:
        raise ProtocolError(
            400,
            UNSUPPORTED_VERSION,
            f"Unsupported protocol version {version}",
            {"supported": SUPPORTED, "requested": version},
            rid,
        )
    expected = {"mcp-protocol-version": version, "mcp-method": method}
    if method in ("tools/call", "prompts/get"):
        expected["mcp-name"] = str(params.get("name", ""))
    elif method == "resources/read":
        expected["mcp-name"] = str(params.get("uri", ""))
    for name, want in expected.items():
        got = headers.get(name)
        if got is None:
            raise ProtocolError(400, HEADER_MISMATCH, f"Missing required header {name}", rid=rid)
        if (decode_header(got) if name == "mcp-name" else got) != want:
            raise ProtocolError(400, HEADER_MISMATCH, f"Header mismatch: {name} does not match the body", rid=rid)
    return params


def check_param_headers(headers, schema: dict | None, args: dict, rid) -> None:
    """A server that processes the body MUST check recognized Mcp-Param-* headers against it."""
    for name, path in header_params(schema).items():
        value, got = value_at(args, path), headers.get(f"mcp-param-{name}")
        if value is None:
            continue
        if got is None:
            raise ProtocolError(400, HEADER_MISMATCH, f"Missing Mcp-Param-{name} header", rid=rid)
        want = "true" if value is True else "false" if value is False else str(value)
        if decode_header(got) != want:
            raise ProtocolError(400, HEADER_MISMATCH, f"Header mismatch: Mcp-Param-{name}", rid=rid)


def request_meta(extra: dict | None = None) -> dict:
    return {
        META + "protocolVersion": PROTOCOL,
        META + "clientInfo": {"name": "checkpoint", "version": "0.1.0"},
        META + "clientCapabilities": {},
    } | (extra or {})


def result(rid, payload: dict) -> dict:
    meta = {META + "serverInfo": {"name": "checkpoint", "version": "0.1.0"}}
    return {"jsonrpc": "2.0", "id": rid, "result": {"resultType": "complete"} | payload | {"_meta": meta}}
