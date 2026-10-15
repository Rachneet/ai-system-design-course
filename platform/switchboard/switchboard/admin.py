"""The control plane: tenancy, keys, policies, chargeback. Every write is recorded in admin_audit."""

import hashlib
import hmac
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from psycopg import sql
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .keys import new_key
from .pricing import PRICES

router = APIRouter(prefix="/admin", tags=["admin"])
ID = r"^[a-z0-9][a-z0-9-]{1,62}$"


async def admin(request: Request, authorization: str = Header(default="")) -> str:
    expected = request.app.state.settings.admin_token
    presented = authorization.removeprefix("Bearer ")
    if not expected or not hmac.compare_digest(
        hashlib.sha256(presented.encode()).digest(), hashlib.sha256(expected.encode()).digest()
    ):
        raise HTTPException(401, "Admin token required")
    return "admin"  # with SSO, this would be the operator's identity from the token


async def audit(request: Request, actor: str, action: str, target: str, details: dict) -> None:
    async with request.app.state.pool.connection() as c:
        await c.execute(
            "INSERT INTO admin_audit (actor, action, target, details) VALUES (%s, %s, %s, %s)",
            (actor, action, target, Jsonb(details)),
        )


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrgIn(Strict):
    id: str = Field(pattern=ID)
    name: str = Field(min_length=1, max_length=200)
    budget_usd_month: Decimal | None = Field(default=None, ge=0)


class TeamIn(OrgIn):
    org_id: str = Field(pattern=ID)


class AppPolicy(Strict):
    allowed_models: list[str] = []
    rpm: int = Field(default=60, ge=1, le=100_000)
    tpm: int = Field(default=200_000, ge=1000, le=100_000_000)
    budget_usd_month: Decimal | None = Field(default=None, ge=0)
    pii_mode: Literal["off", "detect", "redact"] = "detect"
    log_bodies: bool = False
    retention_days: int = Field(default=30, ge=1, le=400)

    @field_validator("allowed_models")
    @classmethod
    def models_exist(cls, v: list[str]) -> list[str]:
        unknown = sorted(set(v) - set(PRICES))
        if unknown:
            raise ValueError(f"unknown models: {unknown}")
        return v


class AppIn(AppPolicy):
    id: str = Field(pattern=ID)
    team_id: str = Field(pattern=ID)
    name: str = Field(min_length=1, max_length=200)


class KeyIn(Strict):
    label: str | None = Field(default=None, max_length=100)
    expires_in_days: int | None = Field(default=90, ge=1, le=730)


async def insert(request: Request, actor: str, table: str, values: dict) -> dict:
    query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, values)),
        sql.SQL(", ").join(sql.Placeholder() * len(values)),
    )
    try:
        async with request.app.state.pool.connection() as c:
            await c.execute(query, list(values.values()))
    except Exception as e:  # unique or foreign-key violation
        raise HTTPException(409, f"Could not create {table[:-1]}: {type(e).__name__}") from e
    await audit(request, actor, f"create_{table[:-1]}", values["id"], {k: str(v) for k, v in values.items()})
    return values


@router.post("/orgs", status_code=201)
async def create_org(body: OrgIn, request: Request, actor: str = Depends(admin)):
    return await insert(request, actor, "orgs", body.model_dump())


@router.post("/teams", status_code=201)
async def create_team(body: TeamIn, request: Request, actor: str = Depends(admin)):
    return await insert(request, actor, "teams", body.model_dump())


@router.post("/apps", status_code=201)
async def create_app(body: AppIn, request: Request, actor: str = Depends(admin)):
    return await insert(request, actor, "apps", body.model_dump())


class BudgetIn(Strict):
    budget_usd_month: Decimal | None = Field(ge=0)  # null removes the limit at this level


@router.put("/{scope}/{scope_id}/budget")
async def set_budget(
    scope: Literal["orgs", "teams"], scope_id: str, body: BudgetIn, request: Request, actor: str = Depends(admin)
):
    """Change an org's or team's monthly budget. Apps change theirs through their policy."""
    query = sql.SQL("UPDATE {} SET budget_usd_month = %s WHERE id = %s RETURNING id").format(sql.Identifier(scope))
    async with request.app.state.pool.connection() as c:
        row = await (await c.execute(query, (body.budget_usd_month, scope_id))).fetchone()
    if row is None:
        raise HTTPException(404, f"{scope[:-1].title()} not found")
    request.app.state.gateway.budgets.forget()
    await audit(request, actor, "set_budget", f"{scope}/{scope_id}", {"budget_usd_month": str(body.budget_usd_month)})
    return {"id": scope_id, "budget_usd_month": body.budget_usd_month}


@router.put("/apps/{app_id}/policy")
async def set_policy(app_id: str, body: AppPolicy, request: Request, actor: str = Depends(admin)):
    values = body.model_dump()
    sets = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(k)) for k in values)
    query = sql.SQL("UPDATE apps SET {} WHERE id = %s RETURNING id").format(sets)
    async with request.app.state.pool.connection() as c:
        row = await (await c.execute(query, [*values.values(), app_id])).fetchone()
    if row is None:
        raise HTTPException(404, "App not found")
    request.app.state.gateway.keys.forget()  # this instance applies the change now; others within the cache TTL
    request.app.state.gateway.budgets.forget()
    await audit(request, actor, "set_policy", app_id, {k: str(v) for k, v in values.items()})
    return {"id": app_id, **values}


@router.post("/apps/{app_id}/keys", status_code=201)
async def create_key(app_id: str, body: KeyIn, request: Request, actor: str = Depends(admin)):
    key_id, plaintext, digest = new_key()
    expires = datetime.now(UTC) + timedelta(days=body.expires_in_days) if body.expires_in_days else None
    try:
        async with request.app.state.pool.connection() as c:
            await c.execute(
                "INSERT INTO api_keys (id, app_id, secret_hash, label, expires_at) VALUES (%s, %s, %s, %s, %s)",
                (key_id, app_id, digest, body.label, expires),
            )
    except Exception as e:
        raise HTTPException(404, "App not found") from e
    await audit(request, actor, "create_key", key_id, {"app_id": app_id, "label": body.label})
    return {"id": key_id, "key": plaintext, "expires_at": expires, "note": "Store this key now; it is not shown again."}


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(key_id: str, request: Request, actor: str = Depends(admin)):
    async with request.app.state.pool.connection() as c:
        row = await (
            await c.execute(
                "UPDATE api_keys SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL RETURNING id", (key_id,)
            )
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Key not found or already revoked")
    request.app.state.gateway.keys.forget(key_id)
    await audit(request, actor, "revoke_key", key_id, {})


@router.get("/usage")
async def usage(
    request: Request,
    month: str,
    group_by: Literal["org", "team", "app", "model", "tag"] = "team",
    tag_prefix: str | None = Query(default=None, max_length=128),
    actor: str = Depends(admin),
):
    """Chargeback: cost, requests, tokens and fallbacks per group for one calendar month (YYYY-MM). With
    group_by=tag, cost per unit of work (x-switchboard-tag), optionally only tags starting with tag_prefix."""
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise HTTPException(422, "month must be YYYY-MM")
    column = {
        "org": sql.Identifier("org_id"),
        "team": sql.Identifier("team_id"),
        "app": sql.Identifier("app_id"),
        "model": sql.SQL("coalesce(served_model, requested_model)"),
        "tag": sql.Identifier("tag"),
    }[group_by]
    async with request.app.state.pool.connection() as c:
        rows = await (
            await c.execute(
                sql.SQL(
                    "SELECT {} AS id, count(*) AS requests, sum(cost_usd) AS cost_usd, "
                    "sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens, "
                    "sum(cache_read_tokens) AS cache_read_tokens, count(*) FILTER (WHERE fallback) AS fallbacks, "
                    "count(*) FILTER (WHERE status >= 400) AS errors "
                    "FROM usage_events WHERE ts >= to_date(%s, 'YYYY-MM') AND ts < to_date(%s, 'YYYY-MM') + interval '1 month' "
                    "AND (%s::text IS NULL OR starts_with(tag, %s)) "
                    "GROUP BY 1 ORDER BY sum(cost_usd) DESC"
                ).format(column),
                (month, month, tag_prefix, tag_prefix),
            )
        ).fetchall()
    return {"month": month, "group_by": group_by, "rows": rows}


@router.post("/purge-expired")
async def purge(request: Request, actor: str = Depends(admin)):
    async with request.app.state.pool.connection() as c:
        cur = await c.execute("DELETE FROM audit_bodies WHERE expires_at < now()")
    await audit(request, actor, "purge_expired", "audit_bodies", {"deleted": cur.rowcount})
    return {"deleted": cur.rowcount}
