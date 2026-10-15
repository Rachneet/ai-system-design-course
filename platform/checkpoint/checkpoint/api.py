"""Approvals (people with approver tokens), administration (the admin token), and the public key set upstream
servers use to verify Checkpoint's assertions."""

import hashlib
import hmac
from pathlib import Path
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from .identity import Agent, new_token, resolve
from .policy import Policy, PolicyError

router = APIRouter()
ID = r"^[a-z0-9][a-z0-9-]{1,62}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


async def admin(request: Request, authorization: str = Header(default="")) -> str:
    expected = request.app.state.settings.admin_token
    presented = authorization.removeprefix("Bearer ")
    if not expected or not hmac.compare_digest(
        hashlib.sha256(presented.encode()).digest(), hashlib.sha256(expected.encode()).digest()
    ):
        raise HTTPException(401, "admin token required")
    return "admin"


async def approver(request: Request, authorization: str = Header(default="")) -> Agent:
    who = await resolve(request.app.state.pool, authorization.removeprefix("Bearer ").strip())
    if who is None or who.role != "approver":
        raise HTTPException(401, "an approver token is required")
    return who


ADMIN, APPROVER = Depends(admin), Depends(approver)


@router.get("/.well-known/jwks.json", tags=["identity"])
async def jwks(request: Request):
    return request.app.state.signer.jwks()


async def expire(c) -> None:
    """Lapse requests nobody decided in time and approvals nobody used in time."""
    await c.execute(
        "UPDATE approvals SET status = 'expired' WHERE status IN ('pending', 'approved') AND expires_at <= now()"
    )


@router.get("/approvals", tags=["approvals"])
async def list_approvals(request: Request, status: str = "pending", who: Agent = APPROVER):
    async with request.app.state.pool.connection() as c:
        await expire(c)
        rows = await (
            await c.execute(
                "SELECT id, tenant, agent_id, user_id, tool, args, status, policies, requested_at, decided_by, "
                "decided_at, note, expires_at FROM approvals WHERE status = %s AND (%s::text IS NULL OR tenant = %s) "
                "ORDER BY requested_at LIMIT 200",
                (status, who.tenant, who.tenant),
            )
        ).fetchall()
    return {"approvals": rows}


class DecisionIn(Strict):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=2000)


@router.post("/approvals/{approval_id}/decision", tags=["approvals"])
async def decide(
    approval_id: int,
    body: DecisionIn,
    request: Request,
    who: Agent = APPROVER,
    x_user_token: str | None = Header(default=None),
):
    """An approver decides as itself, or, for a console that serves many people, on behalf of the signed-in person
    in X-User-Token: that person must hold the approver role, belong to the approver's tenant, and is the one
    recorded and checked against the requester."""
    cfg = request.app.state.settings
    person = who.id
    if x_user_token:
        try:
            user = request.app.state.users.verify(x_user_token)
        except jwt.PyJWTError as e:
            raise HTTPException(401, f"invalid user token: {e}") from None
        if cfg.approver_role not in user.roles or (who.tenant and user.tenant != who.tenant):
            raise HTTPException(403, f"the signed-in person needs the {cfg.approver_role} role in this tenant")
        person = user.id
    status = "approved" if body.decision == "approve" else "rejected"
    async with request.app.state.pool.connection() as c:
        await expire(c)
        found = await (
            await c.execute("SELECT status, user_id, tenant FROM approvals WHERE id = %s", (approval_id,))
        ).fetchone()
        if found and who.tenant and found["tenant"] != who.tenant:
            found = None  # another tenant's request: indistinguishable from an unknown id
        if found and found["user_id"] == person:
            raise HTTPException(403, "you cannot decide a request made on your own behalf")
        decided_by = person if person == who.id else f"{person} via {who.id}"
        row = await (
            await c.execute(
                "UPDATE approvals SET status = %s, decided_by = %s, decided_at = now(), note = %s, "
                "expires_at = CASE WHEN %s = 'approved' THEN now() + make_interval(secs => %s) ELSE expires_at END "
                "WHERE id = %s AND status = 'pending' AND (%s::text IS NULL OR tenant = %s) "
                "RETURNING id, status, tool, user_id, expires_at",
                (status, decided_by, body.note, status, cfg.approval_use_ttl_s, approval_id, who.tenant, who.tenant),
            )
        ).fetchone()
    if not row:
        lapsed = found and found["status"] == "expired"
        raise HTTPException(409, "expired" if lapsed else "not pending (already decided, used, or unknown)")
    return row


class AgentIn(Strict):
    id: str = Field(pattern=ID)
    role: Literal["agent", "approver"] = "agent"
    tenant: str | None = Field(default=None, pattern=ID)  # bind an agent (or approver) to one tenant


@router.post("/admin/agents", status_code=201, tags=["admin"])
async def create_agent(body: AgentIn, request: Request, _: str = ADMIN):
    tid, token, hashed = new_token()
    async with request.app.state.pool.connection() as c:
        exists = await (await c.execute("SELECT 1 FROM agents WHERE id = %s", (body.id,))).fetchone()
        if exists:
            raise HTTPException(409, "agent exists; revoke it to rotate")
        await c.execute(
            "INSERT INTO agents (id, role, tenant, token_hash) VALUES (%s, %s, %s, %s)",
            (body.id, body.role, body.tenant, hashed),
        )
    # The token id is the agent id, so policies name agents by a stable, readable id.
    token = token.replace(f"ckp_{tid}_", f"ckp_{body.id}_", 1)
    return {"id": body.id, "tenant": body.tenant, "token": token, "note": "shown once"}


@router.delete("/admin/agents/{agent_id}", status_code=204, tags=["admin"])
async def revoke_agent(agent_id: str, request: Request, _: str = ADMIN):
    async with request.app.state.pool.connection() as c:
        await c.execute("UPDATE agents SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL", (agent_id,))
    return Response(status_code=204)


@router.post("/admin/policy/reload", tags=["admin"])
async def reload_policy(request: Request, _: str = ADMIN):
    """Load the policy file again; a file that does not parse leaves the running policy in place."""
    try:
        request.app.state.policy = Policy(Path(request.app.state.settings.policy_file).read_text())
    except (OSError, PolicyError) as e:
        raise HTTPException(422, str(e)) from None
    return {"policies": len(request.app.state.policy.annotations)}


@router.get("/admin/decisions", tags=["admin"])
async def decisions(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    tenant: str | None = None,
    user: str | None = None,
    _: str = ADMIN,
):
    async with request.app.state.pool.connection() as c:
        rows = await (
            await c.execute(
                "SELECT * FROM decisions WHERE (%s::text IS NULL OR tenant = %s) AND (%s::text IS NULL OR user_id = %s) "
                "ORDER BY id DESC LIMIT %s",
                (tenant, tenant, user, user, limit),
            )
        ).fetchall()
    return {"decisions": rows}
