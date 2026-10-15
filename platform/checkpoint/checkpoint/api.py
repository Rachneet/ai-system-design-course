"""Approvals (people with approver tokens), administration (the admin token), and the public key set upstream
servers use to verify Checkpoint's assertions."""

import hashlib
import hmac
from pathlib import Path
from typing import Literal

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


@router.get("/approvals", tags=["approvals"])
async def list_approvals(request: Request, status: str = "pending", who: Agent = APPROVER):
    async with request.app.state.pool.connection() as c:
        rows = await (
            await c.execute(
                "SELECT id, agent_id, user_id, tool, args, status, policies, requested_at, decided_by, decided_at, note "
                "FROM approvals WHERE status = %s ORDER BY requested_at LIMIT 200",
                (status,),
            )
        ).fetchall()
    return {"approvals": rows}


class DecisionIn(Strict):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=2000)


@router.post("/approvals/{approval_id}/decision", tags=["approvals"])
async def decide(approval_id: int, body: DecisionIn, request: Request, who: Agent = APPROVER):
    status = "approved" if body.decision == "approve" else "rejected"
    async with request.app.state.pool.connection() as c:
        row = await (
            await c.execute(
                "UPDATE approvals SET status = %s, decided_by = %s, decided_at = now(), note = %s "
                "WHERE id = %s AND status = 'pending' RETURNING id, status, tool, user_id",
                (status, who.id, body.note, approval_id),
            )
        ).fetchone()
    if not row:
        raise HTTPException(409, "not pending (already decided, used, or unknown)")
    return row


class AgentIn(Strict):
    id: str = Field(pattern=ID)
    role: Literal["agent", "approver"] = "agent"


@router.post("/admin/agents", status_code=201, tags=["admin"])
async def create_agent(body: AgentIn, request: Request, _: str = ADMIN):
    tid, token, hashed = new_token()
    async with request.app.state.pool.connection() as c:
        exists = await (await c.execute("SELECT 1 FROM agents WHERE id = %s", (body.id,))).fetchone()
        if exists:
            raise HTTPException(409, "agent exists; revoke it to rotate")
        await c.execute("INSERT INTO agents (id, role, token_hash) VALUES (%s, %s, %s)", (body.id, body.role, hashed))
    # The token id is the agent id, so policies name agents by a stable, readable id.
    return {"id": body.id, "token": token.replace(f"ckp_{tid}_", f"ckp_{body.id}_", 1), "note": "shown once"}


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
async def decisions(request: Request, limit: int = Query(default=100, ge=1, le=1000), _: str = ADMIN):
    async with request.app.state.pool.connection() as c:
        rows = await (await c.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT %s", (limit,))).fetchall()
    return {"decisions": rows}
