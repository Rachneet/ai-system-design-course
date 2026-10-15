"""Cost per resolved ticket, per tenant and per agent.

Model cost comes from Switchboard's ledger: every model call carries x-switchboard-tag ticket:<ticket>:<agent>, and
GET /admin/usage?group_by=tag returns cost per tag. Outcomes come from Helpdesk's tickets. A ticket counts as resolved
when it is resolved and was not reopened within the reopen window. People's time is added at the assumed costs in
settings (HUMAN_COST_PER_ESCALATION_USD, HUMAN_COST_PER_APPROVAL_USD), reported as assumptions, never as measurements.
"""

import re
from collections import defaultdict

from fastapi import HTTPException

from .db import tenant


async def usage_by_ticket(state, month: str) -> dict[tuple[str, str], tuple[float, int]]:
    """(ticket id, agent id) -> (cost in USD, requests), from Switchboard."""
    resp = await state.switchboard.client.get(
        "/admin/usage",
        params={"month": month, "group_by": "tag", "tag_prefix": "ticket:"},
        headers={"authorization": f"Bearer {state.settings.switchboard_admin_token}"},
    )
    if resp.status_code != 200:
        raise HTTPException(502, f"Switchboard usage report failed with {resp.status_code}")
    out = {}
    for row in resp.json()["rows"]:
        parts = (row["id"] or "").split(":")
        if len(parts) == 3:
            out[(parts[1], parts[2])] = (float(row["cost_usd"] or 0), int(row["requests"]))
    return out


async def report(state, month: str) -> dict:
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise HTTPException(422, "month must be YYYY-MM")
    cfg, usage = state.settings, await usage_by_ticket(state, month)
    tenants, agents = [], defaultdict(lambda: {"model_cost_usd": 0.0, "requests": 0, "resolved": 0})
    for name in state.roster.tenants:
        async with tenant(state.pool, name) as c:
            tickets = await (
                await c.execute(
                    "SELECT t.id, t.status, t.resolved_by, t.reopened_at, "
                    "(SELECT count(*) FROM escalations e WHERE e.ticket_id = t.id) AS escalations, "
                    "(SELECT count(*) FROM events v WHERE v.ticket_id = t.id AND v.kind = 'approval' "
                    "AND v.detail ? 'approved') AS approvals "
                    "FROM tickets t WHERE t.created_at >= to_date(%s, 'YYYY-MM') "
                    "AND t.created_at < to_date(%s, 'YYYY-MM') + interval '1 month'",
                    (month, month),
                )
            ).fetchall()
        ids = {t["id"] for t in tickets}
        model = sum(cost for (tid, _), (cost, _) in usage.items() if tid in ids)
        escalations = sum(t["escalations"] for t in tickets)
        approvals = sum(t["approvals"] for t in tickets)
        human = escalations * cfg.human_cost_per_escalation_usd + approvals * cfg.human_cost_per_approval_usd
        resolved = [t for t in tickets if t["status"] == "resolved" and t["reopened_at"] is None]
        for (tid, agent), (cost, requests) in usage.items():
            if tid in ids:
                agents[agent]["model_cost_usd"] += cost
                agents[agent]["requests"] += requests
        for t in resolved:
            if t["resolved_by"] in state.roster.agents:
                agents[t["resolved_by"]]["resolved"] += 1
        tenants.append(
            {
                "tenant": name,
                "tickets": len(tickets),
                "resolved": len(resolved),
                "resolution_rate": round(len(resolved) / len(tickets), 3) if tickets else None,
                "escalations": escalations,
                "approvals": approvals,
                "model_cost_usd": round(model, 6),
                "human_cost_usd": round(human, 2),
                "cost_per_resolved_usd": round((model + human) / len(resolved), 4) if resolved else None,
            }
        )
    return {
        "month": month,
        "assumptions": {
            "human_cost_per_escalation_usd": cfg.human_cost_per_escalation_usd,
            "human_cost_per_approval_usd": cfg.human_cost_per_approval_usd,
            "resolved": f"resolved and not reopened within {cfg.reopen_window_days} days",
        },
        "tenants": tenants,
        "agents": [
            {
                "agent": a,
                "tenant": state.roster.agents[a].tenant if a in state.roster.agents else None,
                **v,
                "model_cost_per_resolved_usd": round(v["model_cost_usd"] / v["resolved"], 4) if v["resolved"] else None,
            }
            for a, v in sorted(agents.items())
        ],
    }
