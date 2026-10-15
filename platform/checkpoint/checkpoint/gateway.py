"""POST /mcp: the one endpoint agents use. Every tool call passes, in order:

1. transport rules     headers must match the body (MCP 2026-07-28); unknown versions and methods rejected
2. agent identity      the agent's own token; approvers cannot call tools
3. user identity       the end user's JWT (X-User-Token), verified, if the agent acts for someone
4. catalog             only tools of servers approved in Atlas exist
5. rate limit          per agent and tool
6. Cedar policy        allow, deny, or allow-after-approval, from the agent, tool, arguments and user
7. upstream call       with a short-lived assertion naming user and agent; the agent never holds credentials
8. output scan         hidden Unicode removed, secrets redacted, instruction-like text marked
9. decision log        every outcome, with the policies that produced it
"""

import hashlib
import json
import time

import httpx
import jwt
import structlog
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from psycopg.types.json import Jsonb

from . import mcp, metrics
from .api import expire
from .catalog import SEP
from .identity import Agent, User, resolve
from .scan import scan_result
from .upstream import UpstreamError

log = structlog.get_logger("checkpoint")
APPROVAL_KEY = "io.checkpoint/approvalId"


def tool_error(rid, text: str, extra: dict | None = None) -> dict:
    """Policy outcomes are tool results with isError, so the model can read them and adapt, not protocol errors."""
    return mcp.result(rid, {"content": [{"type": "text", "text": text}], "isError": True} | (extra or {}))


def args_digest(tool: str, args: dict) -> str:
    return hashlib.sha256(json.dumps([tool, args], sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def record(
    pool, agent: Agent, user: User | None, action, tool, decision, policies=(), flags=(), started=None, errors=()
):
    latency = int((time.perf_counter() - started) * 1000) if started else None
    async with pool.connection() as c:
        await c.execute(
            "INSERT INTO decisions (agent_id, user_id, action, tool, decision, policies, flags, latency_ms, errors) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                agent.id,
                user.id if user else None,
                action,
                tool,
                decision,
                list(policies),
                list(flags),
                latency,
                list(errors),
            ),
        )
    metrics.decisions.labels(action=action, decision=decision).inc()
    if errors:
        metrics.policy_errors.inc(len(errors))
        log.warning("policy_errors", agent=agent.id, tool=tool, decision=decision, errors=list(errors))


def context(user: User | None, args: dict, server: str) -> dict:
    return {
        "args": args,
        "user": {"id": user.id if user else "", "roles": list(user.roles) if user else []},
        "server": server,
    }


async def handle(request: Request) -> Response:
    state, cfg = request.app.state, request.app.state.settings
    origin = request.headers.get("origin")
    if origin and origin not in cfg.allowed_origins:
        return JSONResponse(mcp.ProtocolError(403, mcp.INVALID_REQUEST, "Origin not allowed").body(), status_code=403)

    presented = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    agent = await resolve(state.pool, presented) if presented else None
    if agent is None or agent.role != "agent":
        return JSONResponse(
            {"error": "an agent token is required"},
            status_code=401,
            headers={"www-authenticate": 'Bearer realm="checkpoint"'},
        )

    try:
        body = json.loads(await request.body())
    except ValueError:
        return JSONResponse(mcp.ProtocolError(400, mcp.PARSE_ERROR, "Parse error").body(), status_code=400)
    if isinstance(body, dict) and "id" not in body:
        return Response(status_code=202)  # notifications: accepted, nothing to answer

    try:
        params = mcp.validate(request.headers, body)
    except mcp.ProtocolError as e:
        return JSONResponse(e.body(), status_code=e.status)
    rid, method = body["id"], body["method"]

    user = None
    if request.headers.get("x-user-token"):
        try:
            user = state.users.verify(request.headers["x-user-token"])
        except jwt.PyJWTError as e:
            return JSONResponse(
                mcp.ProtocolError(401, mcp.INVALID_PARAMS, f"invalid user token: {e}", rid=rid).body(), status_code=401
            )

    if method == "ping":
        return JSONResponse(mcp.result(rid, {}))
    if method == "tools/list":
        await state.catalog.refresh()
        tools = []
        for name, server, tool in state.catalog.all_tools():
            if state.policy.decide(agent.id, "list", name, context(user, {}, server.name)).allowed:
                tools.append(
                    tool | {"name": name, "description": f"[{server.name}] {tool.get('description', '')}".strip()}
                )
        return JSONResponse(mcp.result(rid, {"tools": tools}))
    if method != "tools/call":
        e = mcp.ProtocolError(404, mcp.METHOD_NOT_FOUND, f"Method not found: {method}", rid=rid)
        return JSONResponse(e.body(), status_code=404)
    try:
        return JSONResponse(await call_tool(request, rid, params, agent, user))
    except mcp.ProtocolError as e:
        return JSONResponse(e.body(), status_code=e.status)


async def call_tool(request: Request, rid, params: dict, agent: Agent, user: User | None) -> dict:
    state, started = request.app.state, time.perf_counter()
    name, args = params.get("name", ""), params.get("arguments") or {}
    if not isinstance(args, dict):
        raise mcp.ProtocolError(400, mcp.INVALID_PARAMS, "arguments must be an object", rid=rid)
    await state.catalog.refresh()
    found = state.catalog.find(name)
    if not found:
        await state.catalog.refresh(force=True)  # a server may have been approved since the last refresh
        found = state.catalog.find(name)
    if not found and (drifted := state.catalog.quarantined(name)):
        await record(state.pool, agent, user, "call", name, "tools_changed", started=started)
        return tool_error(
            rid,
            f"The {drifted.name} server's tools changed since they were reviewed, so its tools are unavailable until "
            "a version with the new tools is approved. Do not retry; tell the user this action is unavailable.",
        )
    if not found:
        await record(state.pool, agent, user, "call", name, "unknown_tool", started=started)
        raise mcp.ProtocolError(
            200, mcp.INVALID_PARAMS, f"Unknown tool: {name}", rid=rid
        )  # a JSON-RPC error, not a transport one
    server, tool = found
    mcp.check_param_headers(request.headers, tool.get("inputSchema"), args, rid)

    wait = state.limits.take(f"{agent.id}:{name}")
    if wait:
        await record(state.pool, agent, user, "call", name, "rate_limited", started=started)
        return tool_error(rid, f"Rate limit reached for {name}. Retry in {int(wait) + 1} s.")

    decision = state.policy.decide(agent.id, "call", name, context(user, args, server.name))
    if not decision.allowed:
        await record(
            state.pool, agent, user, "call", name, "deny", decision.policies, started=started, errors=decision.errors
        )
        why = f" by {', '.join(decision.policies)}" if decision.policies else " (no policy permits it)"
        return tool_error(rid, f"Denied{why}. Do not retry; explain to the user that this action is not allowed.")

    if decision.needs_approval:
        held = await approval_gate(state, rid, params, agent, user, name, args, decision.policies)
        if held is not None:
            await record(
                state.pool,
                agent,
                user,
                "call",
                name,
                "hold",
                decision.policies,
                started=started,
                errors=decision.errors,
            )
            return held

    upstream_tool = name.split(SEP, 1)[1]
    headers = mcp.param_headers(tool.get("inputSchema"), args) | {
        "x-checkpoint-assertion": state.signer.assertion(server.name, upstream_tool, agent, user)
    }
    meta = {k: v for k, v in (params.get("_meta") or {}).items() if k in ("traceparent", "tracestate")}
    t0 = time.perf_counter()
    try:
        result = await server.upstream.call("tools/call", {"name": upstream_tool, "arguments": args}, headers, meta)
    except (UpstreamError, httpx.HTTPError) as e:
        await record(state.pool, agent, user, "call", name, "error", decision.policies, started=started)
        log.warning("upstream_error", server=server.name, tool=upstream_tool, error=str(e))
        return tool_error(rid, f"The {server.name} server failed: {e}")
    finally:
        metrics.upstream_seconds.labels(server=server.name).observe(time.perf_counter() - t0)
    result.pop("_meta", None)
    result.pop("resultType", None)
    cleaned, flags = scan_result(result)
    for f in flags:
        metrics.flags.labels(flag=f).inc()
    outcome = "approved" if decision.needs_approval else "allow"
    await record(state.pool, agent, user, "call", name, outcome, decision.policies, flags, started, decision.errors)
    response = mcp.result(rid, cleaned)
    if flags:
        response["result"]["_meta"]["io.checkpoint/flags"] = flags
    return response


async def approval_gate(state, rid, params, agent: Agent, user: User | None, name, args, policies) -> dict | None:
    """None lets the call through (a matching, unexpired approval was found and consumed); otherwise a held result."""
    if user is None:
        return tool_error(rid, "This action needs a person's approval, which requires a signed-in user.")
    digest = args_digest(name, args)
    approval_id = (params.get("_meta") or {}).get(APPROVAL_KEY)
    async with state.pool.connection() as c, c.transaction():
        await expire(c)
        if approval_id is not None:
            used = await (
                await c.execute(
                    "UPDATE approvals SET status = 'used', used_at = now() WHERE id = %s AND status = 'approved' "
                    "AND agent_id = %s AND user_id = %s AND args_digest = %s AND expires_at > now() RETURNING id",
                    (approval_id, agent.id, user.id, digest),
                )
            ).fetchone()
            if used:
                return None
        row = await (
            await c.execute(
                "SELECT id, status, expires_at FROM approvals WHERE agent_id = %s AND user_id = %s "
                "AND args_digest = %s AND status IN ('pending', 'approved') ORDER BY id DESC LIMIT 1",
                (agent.id, user.id, digest),
            )
        ).fetchone()
        if not row:
            row = await (
                await c.execute(
                    "INSERT INTO approvals (agent_id, user_id, tool, args, args_digest, status, policies, expires_at) "
                    "VALUES (%s, %s, %s, %s, %s, 'pending', %s, now() + make_interval(secs => %s)) "
                    "RETURNING id, status, expires_at",
                    (agent.id, user.id, name, Jsonb(args), digest, policies, state.settings.approval_pending_ttl_s),
                )
            ).fetchone()
    status, expires = row["status"], row["expires_at"].isoformat()
    text = (
        f"This call needs a person's approval (request {row['id']}, {status}, expires {expires}). Tell the user it "
        f"is waiting for approval. Once approved, repeat the identical call with _meta "
        f'{{"{APPROVAL_KEY}": {row["id"]}}}. If it expires, the same call makes a new request.'
    )
    return tool_error(
        rid, text, {"structuredContent": {"approvalId": row["id"], "status": status, "expiresAt": expires}}
    )
