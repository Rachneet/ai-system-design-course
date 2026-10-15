"""HTTP API.

Publish     POST /v1/mcp-servers, /v1/agents, /v1/skills (multipart zip)               publisher
Review      POST /v1/artifacts/{kind}/{name}/{version}/review | /deprecate              reviewer | owner
Read        GET  /v1/search, /v1/artifacts/{kind}/{name}/{version}                      any token
Discovery   GET  /v0/servers (MCP registry format), /v1/agents/{id}/agent-card.json,
                 /v1/skills/{name}/{version}.zip                                         approved only
Admin       /admin/teams, /admin/principals, /admin/sync/mcp, /admin/audit             admin
"""

import base64
import json
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field

from . import metrics, store, sync
from .auth import ROLES, Principal, authenticated, new_token, reader, require
from .kinds import KINDS, Invalid, parse_a2a_agent, parse_mcp_server, parse_skill

router = APIRouter()
ID = r"^[a-z0-9][a-z0-9-]{1,62}$"
PUBLISHER, REVIEWER, ADMIN = require("publisher"), require("reviewer"), require("admin")
VISIBLE = ["approved", "deprecated"]  # what readers see; deprecated stays visible so clients can warn


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvalReport(Strict):
    suite: str = Field(min_length=1, max_length=200)
    score: float = Field(ge=0, le=1)
    url: str | None = Field(default=None, max_length=2000)


class McpIn(Strict):
    server: dict
    tools: list | None = Field(default=None, description="The tools/list result to review and pin (remote servers)")
    team_id: str | None = None
    eval: EvalReport | None = None


class AgentIn(Strict):
    id: str
    card: dict
    team_id: str | None = None
    eval: EvalReport | None = None


class ReviewIn(Strict):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=2000)
    acknowledge_warnings: bool = False


class NoteIn(Strict):
    note: str = Field(min_length=1, max_length=2000)


def owning_team(who: Principal, requested: str | None) -> str | None:
    if who.can("admin"):
        return requested or who.team_id
    if not who.team_id:
        raise HTTPException(403, "publisher tokens must belong to a team")
    if requested and requested != who.team_id:
        raise HTTPException(403, "you can only publish for your own team")
    return who.team_id


async def publish(request: Request, parsed, who, team_id, eval_report):
    try:
        return await store.publish(
            request.app.state.pool, parsed, who, team_id, eval_report, request.app.state.settings
        )
    except store.Conflict as e:
        raise HTTPException(409, str(e)) from None
    except store.Forbidden as e:
        raise HTTPException(403, str(e)) from None


def public(row: dict) -> dict:
    return {k: v for k, v in row.items() if k != "id"}


@router.post("/v1/mcp-servers", status_code=201, tags=["publish"])
async def publish_mcp(body: McpIn, request: Request, who: Principal = Depends(PUBLISHER)):
    try:
        parsed = parse_mcp_server(body.server, body.tools)
    except Invalid as e:
        raise HTTPException(422, {"problems": e.problems}) from None
    ev = body.eval.model_dump() if body.eval else None
    return public(await publish(request, parsed, who, owning_team(who, body.team_id), ev))


@router.post("/v1/agents", status_code=201, tags=["publish"])
async def publish_agent(body: AgentIn, request: Request, who: Principal = Depends(PUBLISHER)):
    try:
        parsed = parse_a2a_agent(body.id, body.card)
    except Invalid as e:
        raise HTTPException(422, {"problems": e.problems}) from None
    ev = body.eval.model_dump() if body.eval else None
    return public(await publish(request, parsed, who, owning_team(who, body.team_id), ev))


@router.post("/v1/skills", status_code=201, tags=["publish"])
async def publish_skill(
    request: Request,
    package: UploadFile = File(...),
    version: str = Form(...),
    team_id: str | None = Form(default=None),
    eval: str | None = Form(default=None, description="JSON: {suite, score, url}"),
    who: Principal = Depends(PUBLISHER),
):
    cfg = request.app.state.settings
    blob = await package.read(cfg.max_skill_bytes + 1)
    if len(blob) > cfg.max_skill_bytes:
        raise HTTPException(413, f"package is larger than {cfg.max_skill_bytes} bytes")
    try:
        ev = EvalReport.model_validate_json(eval).model_dump() if eval else None
        parsed = parse_skill(blob, version, cfg.max_skill_bytes, cfg.max_skill_files)
    except Invalid as e:
        raise HTTPException(422, {"problems": e.problems}) from None
    except ValueError as e:
        raise HTTPException(422, {"problems": [f"eval: {e}"]}) from None
    return public(await publish(request, parsed, who, owning_team(who, team_id), ev))


def check_kind(kind: str) -> None:
    if kind not in KINDS:
        raise HTTPException(404, f"unknown kind {kind}")


@router.get("/v1/artifacts/{kind}/{name:path}/versions/{version}", tags=["read"])
async def get_artifact(kind: str, name: str, version: str, request: Request, who=Depends(reader)):
    check_kind(kind)
    art = await store.get(request.app.state.pool, kind, name, version)
    if not art or (art["status"] not in VISIBLE and not can_see_unapproved(who, art)):
        raise HTTPException(404, "not found")
    return public(art)


def can_see_unapproved(who: Principal | None, art: dict) -> bool:
    return bool(who) and (who.can("reviewer") or (who.team_id is not None and who.team_id == art["team_id"]))


@router.get("/v1/search", tags=["read"])
async def search(
    request: Request,
    q: str | None = Query(default=None, max_length=200),
    kind: str | None = None,
    status: Literal["approved", "in_review", "rejected", "deprecated", "any"] = "approved",
    team: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    who=Depends(reader),
):
    if kind:
        check_kind(kind)
    statuses = ["approved", "in_review", "rejected", "deprecated"] if status == "any" else [status]
    if set(statuses) - set(VISIBLE):
        if not who:
            raise HTTPException(401, "a token is needed to see unapproved artifacts")
        if not who.can("reviewer"):
            if not who.team_id:
                raise HTTPException(403, "only reviewers or the owning team can see unapproved artifacts")
            team = who.team_id  # publishers see their own team's queue only
    rows = await store.search(request.app.state.pool, q, kind, statuses, team, limit)
    return {"results": rows}


@router.post("/v1/artifacts/{kind}/{name:path}/versions/{version}/review", tags=["review"])
async def review(
    kind: str, name: str, version: str, body: ReviewIn, request: Request, who: Principal = Depends(REVIEWER)
):
    check_kind(kind)
    try:
        row = await store.review(
            request.app.state.pool,
            kind,
            name,
            version,
            who,
            body.decision == "approve",
            body.note,
            body.acknowledge_warnings,
            request.app.state.settings,
        )
    except LookupError:
        raise HTTPException(404, "not found") from None
    except store.Forbidden as e:
        raise HTTPException(403, str(e)) from None
    except store.Conflict as e:
        raise HTTPException(409, str(e)) from None
    return public(row)


@router.post("/v1/artifacts/{kind}/{name:path}/versions/{version}/deprecate", tags=["review"])
async def deprecate(
    kind: str, name: str, version: str, body: NoteIn, request: Request, who: Principal = Depends(authenticated)
):
    check_kind(kind)
    try:
        return public(await store.deprecate(request.app.state.pool, kind, name, version, who, body.note))
    except LookupError:
        raise HTTPException(404, "not found") from None
    except store.Forbidden as e:
        raise HTTPException(403, str(e)) from None
    except store.Conflict as e:
        raise HTTPException(409, str(e)) from None


# ---------- Discovery: approved artifacts only, in the formats clients already speak ----------


def server_entry(row: dict) -> dict:
    return {
        "server": row["document"],
        "_meta": {
            "io.atlas/review": {
                "status": row["status"],
                "team": row["team_id"],
                "source": row["source"],
                "digest": f"sha256:{row['digest']}",
                "toolsDigest": f"sha256:{row['tools_digest']}" if row["tools_digest"] else None,
                "reviewedBy": row["reviewed_by"],
                "reviewedAt": row["reviewed_at"].isoformat() if row["reviewed_at"] else None,
            }
        },
    }


@router.get("/v0/servers", tags=["discovery"])
async def list_servers(
    request: Request,
    search: str | None = Query(default=None, max_length=200),
    cursor: str | None = None,
    limit: int = Query(default=30, ge=1, le=100),
    version: str | None = None,
    who=Depends(reader),
):
    """MCP registry API shape (servers, metadata.nextCursor), so MCP clients can use Atlas as their registry.
    Only approved servers appear; version=latest keeps the newest approved version of each."""
    after = 0
    if cursor:
        try:
            after = int(base64.urlsafe_b64decode(cursor.encode()).decode())
        except ValueError:
            raise HTTPException(400, "bad cursor") from None
    where, args = [sql.SQL("kind = 'mcp_server' AND status = 'approved' AND id > %s")], [after]
    if search:
        where.append(sql.SQL("name ILIKE %s"))
        args.append(f"%{search}%")
    if version == "latest":
        where.append(
            sql.SQL(
                "id = (SELECT max(a2.id) FROM artifacts a2 WHERE a2.kind = 'mcp_server' AND a2.status = 'approved' "
                "AND a2.name = artifacts.name)"
            )
        )
    async with request.app.state.pool.connection() as c:
        rows = await (
            await c.execute(
                sql.SQL("SELECT * FROM artifacts WHERE {} ORDER BY id LIMIT %s").format(sql.SQL(" AND ").join(where)),
                args + [limit + 1],
            )
        ).fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    metrics.downloads.labels(kind="mcp_server").inc()
    meta = {"count": len(rows)}
    if more:
        meta["nextCursor"] = base64.urlsafe_b64encode(str(rows[-1]["id"]).encode()).decode()
    return {"servers": [server_entry(r) for r in rows], "metadata": meta}


async def latest_approved(request: Request, kind: str, name: str, version: str | None) -> dict:
    sql = "SELECT * FROM artifacts WHERE kind = %s AND name = %s AND status = 'approved'"
    args = [kind, name]
    if version:
        sql += " AND version = %s"
        args.append(version)
    async with request.app.state.pool.connection() as c:
        row = await (await c.execute(sql + " ORDER BY id DESC LIMIT 1", args)).fetchone()
    if not row:
        raise HTTPException(404, "no approved version")
    metrics.downloads.labels(kind=kind).inc()
    return row


@router.get("/v1/agents/{agent_id}/agent-card.json", tags=["discovery"])
async def agent_card(agent_id: str, request: Request, version: str | None = None, who=Depends(reader)):
    row = await latest_approved(request, "a2a_agent", agent_id, version)
    return Response(
        json.dumps(row["document"]),
        media_type="application/json",
        headers={"x-atlas-version": row["version"], "x-atlas-digest": f"sha256:{row['digest']}"},
    )


@router.get("/v1/skills/{name}/{version}.zip", tags=["discovery"])
async def skill_package(name: str, version: str, request: Request, who=Depends(reader)):
    row = await latest_approved(request, "skill", name, version)
    return Response(
        bytes(row["package"]),
        media_type="application/zip",
        headers={
            "x-atlas-digest": f"sha256:{row['digest']}",
            "etag": f'"{row["digest"]}"',
            "content-disposition": f'attachment; filename="{name}-{version}.zip"',
        },
    )


# ---------- Admin ----------


class TeamIn(Strict):
    id: str = Field(pattern=ID)
    name: str = Field(min_length=1, max_length=200)


class PrincipalIn(Strict):
    label: str = Field(min_length=1, max_length=200)
    team_id: str | None = Field(default=None, pattern=ID)
    roles: list[str] = Field(min_length=1)


@router.post("/admin/teams", status_code=201, tags=["admin"])
async def create_team(body: TeamIn, request: Request, who: Principal = Depends(ADMIN)):
    async with request.app.state.pool.connection() as c, c.transaction():
        await c.execute(
            "INSERT INTO teams (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING", (body.id, body.name)
        )
        await store.audit(c, who.id, "create_team", body.id, body.model_dump())
    return body.model_dump()


@router.post("/admin/principals", status_code=201, tags=["admin"])
async def create_principal(body: PrincipalIn, request: Request, who: Principal = Depends(ADMIN)):
    if set(body.roles) - ROLES:
        raise HTTPException(422, f"roles must be among {sorted(ROLES)}")
    if "publisher" in body.roles and not body.team_id:
        raise HTTPException(422, "publishers need a team_id")
    tid, token, hashed = new_token()
    async with request.app.state.pool.connection() as c, c.transaction():
        await c.execute(
            "INSERT INTO principals (id, label, team_id, roles, token_hash) VALUES (%s, %s, %s, %s, %s)",
            (tid, body.label, body.team_id, body.roles, hashed),
        )
        await store.audit(c, who.id, "create_principal", tid, {"label": body.label, "roles": body.roles})
    return {"id": tid, "token": token, "note": "Store the token now; it is not shown again."}


@router.delete("/admin/principals/{pid}", status_code=204, tags=["admin"])
async def revoke_principal(pid: str, request: Request, who: Principal = Depends(ADMIN)):
    async with request.app.state.pool.connection() as c, c.transaction():
        await c.execute("UPDATE principals SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL", (pid,))
        await store.audit(c, who.id, "revoke_principal", pid)
    return Response(status_code=204)


class SyncIn(Strict):
    limit: int = Field(default=50, ge=1, le=1000)
    search: str | None = Field(default=None, max_length=200)


@router.post("/admin/sync/mcp", tags=["admin"])
async def sync_mcp(body: SyncIn, request: Request, who: Principal = Depends(ADMIN)):
    result = await sync.import_mcp(
        request.app.state.pool,
        request.app.state.settings,
        body.limit,
        body.search,
        transport=getattr(request.app.state, "upstream_transport", None),
    )
    async with request.app.state.pool.connection() as c:
        await store.audit(c, who.id, "sync_mcp", request.app.state.settings.upstream_registry_url, result)
    return result


@router.get("/admin/audit", tags=["admin"])
async def audit_log(request: Request, limit: int = Query(default=100, ge=1, le=1000), who=Depends(ADMIN)):
    async with request.app.state.pool.connection() as c:
        rows = await (await c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT %s", (limit,))).fetchall()
    return {"events": rows}
