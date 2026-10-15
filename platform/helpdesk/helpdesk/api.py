"""HTTP API.

Tickets   POST /v1/tickets, GET /v1/tickets[/{id}], POST /v1/tickets/{id}/messages      the signed-in user
Console   /console/approvals, /console/escalations, /console/agents, /console/tickets    approvers and supervisors
Admin     /admin/purge, /admin/finops, /admin/evidence                                   the admin token
Dev       POST /dev/token                                                                only with DEV_TOKENS

Everything a user or console member sees is scoped to their tenant by row-level security, not only by WHERE clauses.
"""

import hashlib
import hmac
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field

from . import evidence, finops
from .db import tenant
from .identity import User, mint

router = APIRouter()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


async def signed_in(request: Request, authorization: str = Header(default="")) -> User:
    try:
        return request.app.state.users.verify(authorization.removeprefix("Bearer ").strip())
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"sign in first ({e})", headers={"www-authenticate": "Bearer"}) from None


def role(name: str):
    async def check(user: User = Depends(signed_in)) -> User:
        if not user.has(name):
            raise HTTPException(403, f"the {name} role is required")
        return user

    return check


async def admin(request: Request, authorization: str = Header(default="")) -> None:
    expected = request.app.state.settings.admin_token
    presented = authorization.removeprefix("Bearer ")
    if not expected or not hmac.compare_digest(
        hashlib.sha256(presented.encode()).digest(), hashlib.sha256(expected.encode()).digest()
    ):
        raise HTTPException(401, "admin token required")


USER, APPROVER, SUPERVISOR, ADMIN = (
    Depends(signed_in),
    Depends(role("approver")),
    Depends(role("supervisor")),
    Depends(admin),
)


# ---------- Tickets ----------


class MessageIn(Strict):
    message: str = Field(min_length=1, max_length=4000)


async def view(request: Request, user: User, ticket_id: str) -> dict:
    async with tenant(request.app.state.pool, user.tenant) as c:
        t = await (
            await c.execute(
                "SELECT id, status, agent_id, created_at, updated_at FROM tickets WHERE id = %s AND user_id = %s",
                (ticket_id, user.id),
            )
        ).fetchone()
        if t is None:
            raise HTTPException(404, "no such ticket")
        rows = await (
            await c.execute(
                "SELECT role, content, created_at FROM messages WHERE ticket_id = %s AND role IN ('user', 'assistant') "
                "AND content IS NOT NULL AND content <> '' ORDER BY id",
                (ticket_id,),
            )
        ).fetchall()
    return t | {"messages": [{"role": r["role"], "text": r["content"], "at": r["created_at"]} for r in rows]}


@router.post("/v1/tickets", status_code=201, tags=["tickets"])
async def open_ticket(body: MessageIn, request: Request, user: User = USER):
    tid = await request.app.state.runtime.open(user, body.message)
    return await view(request, user, tid)


@router.get("/v1/tickets", tags=["tickets"])
async def my_tickets(request: Request, user: User = USER):
    async with tenant(request.app.state.pool, user.tenant) as c:
        rows = await (
            await c.execute(
                "SELECT id, status, agent_id, created_at, updated_at FROM tickets WHERE user_id = %s "
                "ORDER BY created_at DESC LIMIT 50",
                (user.id,),
            )
        ).fetchall()
    return {"tickets": rows}


@router.get("/v1/tickets/{ticket_id}", tags=["tickets"])
async def get_ticket(ticket_id: str, request: Request, user: User = USER):
    await request.app.state.runtime.visit(user, ticket_id)
    return await view(request, user, ticket_id)


@router.post("/v1/tickets/{ticket_id}/messages", tags=["tickets"])
async def post_message(ticket_id: str, body: MessageIn, request: Request, user: User = USER):
    try:
        await request.app.state.runtime.post(user, ticket_id, body.message)
    except LookupError:
        raise HTTPException(404, "no such ticket") from None
    return await view(request, user, ticket_id)


# ---------- Console: approvals ----------


def console_token(request: Request, person: User) -> str:
    token = request.app.state.settings.console_tokens.get(person.tenant)
    if not token:
        raise HTTPException(503, f"no Checkpoint console token configured for tenant {person.tenant}")
    return token


@router.get("/console/approvals", tags=["console"])
async def approvals(request: Request, person: User = APPROVER):
    resp = await request.app.state.checkpoint.client.get(
        "/approvals", headers={"authorization": f"Bearer {console_token(request, person)}"}
    )
    if resp.status_code != 200:
        raise HTTPException(502, f"Checkpoint answered {resp.status_code}")
    rows = resp.json()["approvals"]
    async with tenant(request.app.state.pool, person.tenant) as c:
        pending = await (await c.execute("SELECT approval_id, ticket_id FROM pending_calls")).fetchall()
    tickets = {p["approval_id"]: p["ticket_id"] for p in pending}
    return {"approvals": [r | {"ticket_id": tickets.get(r["id"])} for r in rows]}


class DecisionIn(Strict):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=2000)


@router.post("/console/approvals/{approval_id}/decision", tags=["console"])
async def decide(approval_id: int, body: DecisionIn, request: Request, person: User = APPROVER):
    """Checkpoint records the decision against this person (and refuses their own requests); then the held call
    runs once, with exactly the approved arguments, and the agent finishes the ticket."""
    resp = await request.app.state.checkpoint.client.post(
        f"/approvals/{approval_id}/decision",
        json=body.model_dump(),
        headers={"authorization": f"Bearer {console_token(request, person)}", "x-user-token": person.token},
    )
    if resp.status_code != 200:
        raise HTTPException(resp.status_code, resp.json().get("detail", "Checkpoint refused the decision"))
    ticket = await request.app.state.runtime.decided(
        person.tenant, approval_id, body.decision == "approve", person.id, body.note
    )
    return {"approval": resp.json(), "ticket_id": ticket}


# ---------- Console: escalations, kill switches, traces ----------


@router.get("/console/escalations", tags=["console"])
async def escalations(request: Request, person: User = SUPERVISOR):
    async with tenant(request.app.state.pool, person.tenant) as c:
        rows = await (
            await c.execute(
                "SELECT e.id, e.ticket_id, e.agent_id, e.reason, e.summary, e.created_at, t.user_id "
                "FROM escalations e JOIN tickets t ON t.id = e.ticket_id WHERE e.status = 'open' ORDER BY e.created_at"
            )
        ).fetchall()
    return {"escalations": [r | {"trace": f"/console/tickets/{r['ticket_id']}/trace"} for r in rows]}


class ResolveIn(Strict):
    reply: str = Field(min_length=1, max_length=4000)
    note: str = Field(default="", max_length=2000)


@router.post("/console/escalations/{escalation_id}/resolve", tags=["console"])
async def resolve_escalation(escalation_id: int, body: ResolveIn, request: Request, person: User = SUPERVISOR):
    rt = request.app.state.runtime
    async with tenant(request.app.state.pool, person.tenant) as c:
        e = await (
            await c.execute(
                "UPDATE escalations SET status = 'resolved', resolved_by = %s, resolved_at = now(), note = %s "
                "WHERE id = %s AND status = 'open' RETURNING ticket_id",
                (person.id, body.note, escalation_id),
            )
        ).fetchone()
        if e is None:
            raise HTTPException(404, "no open escalation with that id")
        t = await rt.load(c, person.tenant, e["ticket_id"])
        await rt.say(c, t, "assistant", body.reply, f"human:{person.id}")
        await c.execute(
            "UPDATE tickets SET status = 'resolved', resolved_by = 'human', resolved_at = now(), updated_at = now() "
            "WHERE id = %s",
            (t["id"],),
        )
        await rt.event(c, t, "resolution", None, by=person.id, status="resolved", human=True)
    return {"ticket_id": t["id"], "status": "resolved"}


@router.get("/console/agents", tags=["console"])
async def agents(request: Request, person: User = SUPERVISOR):
    roster = request.app.state.roster
    async with request.app.state.pool.connection() as c:
        switches = {r["agent_id"]: r for r in await (await c.execute("SELECT * FROM agent_switches")).fetchall()}
    return {
        "agents": [
            {
                "id": a.id,
                "model": a.model,
                "description": a.description,
                "enabled": switches.get(a.id, {}).get("enabled", True),
            }
            for a in roster.agents.values()
            if a.tenant == person.tenant
        ]
    }


class SwitchIn(Strict):
    enabled: bool
    reason: str = Field(min_length=1, max_length=500)


@router.put("/console/agents/{agent_id}/switch", tags=["console"])
async def switch(agent_id: str, body: SwitchIn, request: Request, person: User = SUPERVISOR):
    """The kill switch: a switched-off agent takes no turns; its tickets go to people until it is switched on."""
    spec = request.app.state.roster.agents.get(agent_id)
    if spec is None or spec.tenant != person.tenant:
        raise HTTPException(404, "no such agent in your tenant")
    async with tenant(request.app.state.pool, person.tenant) as c:
        await c.execute(
            "INSERT INTO agent_switches (agent_id, enabled, reason, changed_by) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (agent_id) DO UPDATE SET enabled = EXCLUDED.enabled, reason = EXCLUDED.reason, "
            "changed_by = EXCLUDED.changed_by, changed_at = now()",
            (agent_id, body.enabled, body.reason, person.id),
        )
        await request.app.state.runtime.event(
            c,
            {"id": None, "tenant": person.tenant},
            "switch",
            agent_id,
            enabled=body.enabled,
            reason=body.reason,
            by=person.id,
        )
    return {"agent_id": agent_id, "enabled": body.enabled}


@router.get("/console/tickets/{ticket_id}/trace", tags=["console"])
async def trace(ticket_id: str, request: Request, person: User = SUPERVISOR):
    """One ticket from start to end: the transcript every agent saw, every model and tool call, every handoff,
    approval and escalation, in order."""
    async with tenant(request.app.state.pool, person.tenant) as c:
        t = await (await c.execute("SELECT * FROM tickets WHERE id = %s", (ticket_id,))).fetchone()
        if t is None:
            raise HTTPException(404, "no such ticket")
        messages = await (
            await c.execute("SELECT * FROM messages WHERE ticket_id = %s ORDER BY id", (ticket_id,))
        ).fetchall()
        events = await (
            await c.execute("SELECT * FROM events WHERE ticket_id = %s ORDER BY id", (ticket_id,))
        ).fetchall()
        escalated = await (
            await c.execute("SELECT * FROM escalations WHERE ticket_id = %s ORDER BY id", (ticket_id,))
        ).fetchall()
    return {"ticket": t, "messages": messages, "events": events, "escalations": escalated}


# ---------- Admin ----------


@router.post("/admin/purge", tags=["admin"])
async def purge(request: Request, _: None = ADMIN):
    """Retention: delete transcript, trace and escalation rows older than their configured period, per tenant."""
    cfg, out = request.app.state.settings, []
    column = {"messages": "created_at", "events": "ts", "escalations": "created_at"}
    for name in request.app.state.roster.tenants:
        async with tenant(request.app.state.pool, name) as c:
            for table, days in cfg.retention_days.items():
                query = sql.SQL("DELETE FROM {} WHERE {} < now() - make_interval(days => %s)").format(
                    sql.Identifier(table), sql.Identifier(column[table])
                )
                cur = await c.execute(query, (days,))
                await c.execute(
                    "INSERT INTO purge_runs (tenant, table_name, older_than_days, deleted) VALUES (%s, %s, %s, %s)",
                    (name, table, days, cur.rowcount),
                )
                out.append({"tenant": name, "table": table, "older_than_days": days, "deleted": cur.rowcount})
    return {"purged": out}


@router.get("/admin/finops", tags=["admin"])
async def finops_report(month: str, request: Request, _: None = ADMIN):
    return await finops.report(request.app.state, month)


@router.get("/admin/evidence", tags=["admin"])
async def evidence_pack(request: Request, ticket_id: str | None = None, _: None = ADMIN):
    return await evidence.pack(request.app.state, ticket_id)


# ---------- Development ----------


class DevTokenIn(Strict):
    sub: str = Field(pattern=r"^[a-z0-9-]{2,40}$")
    tenant: str
    roles: list[str] = []
    name: str = ""


@router.post("/dev/token", tags=["dev"], include_in_schema=False)
async def dev_token(body: DevTokenIn, request: Request):
    cfg = request.app.state.settings
    if not cfg.dev_tokens or not cfg.user_jwt_secret:
        raise HTTPException(404, "not found")
    if body.tenant not in request.app.state.roster.tenants:
        raise HTTPException(422, "unknown tenant")
    return {"token": mint(cfg.user_jwt_secret, body.sub, body.tenant, body.roles, body.name)}
