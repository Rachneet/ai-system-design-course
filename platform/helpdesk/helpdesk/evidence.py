"""The evidence pack, generated from the running system rather than typed: inventory from Atlas, risk assessments and
configuration digests from the roster, decisions from Checkpoint, a ticket reconstructed from start to end,
retention settings with the purge history, and the AI disclosure each front end shows."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from .db import tenant
from .web import DISCLOSURE


def digest(path: str | Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


async def get(client, path: str, token: str, **params) -> dict:
    resp = await client.get(path, params=params, headers={"authorization": f"Bearer {token}"})
    return resp.json() if resp.status_code == 200 else {"error": f"{path} answered {resp.status_code}"}


async def pack(state, ticket_id: str | None = None) -> dict:
    cfg, roster = state.settings, state.roster
    # A reader token sees what agents may use (approved) and what is being retired (deprecated); no reviewer rights.
    inventory = []
    for status in ("approved", "deprecated"):
        found = await get(state.atlas, "/v1/search", cfg.atlas_token, status=status, limit=100)
        inventory += found.get("results", [found])
    decisions = await get(state.checkpoint.client, "/admin/decisions", cfg.checkpoint_admin_token, limit=1000)
    counts: dict[str, dict[str, int]] = {}
    for d in decisions.get("decisions", []):
        per = counts.setdefault(d.get("tenant") or "none", {})
        per[d["decision"]] = per.get(d["decision"], 0) + 1

    reconstruction = None
    if ticket_id:
        for name in roster.tenants:
            async with tenant(state.pool, name) as c:
                t = await (await c.execute("SELECT * FROM tickets WHERE id = %s", (ticket_id,))).fetchone()
                if t is None:
                    continue
                events = await (
                    await c.execute(
                        "SELECT ts, kind, agent_id, detail FROM events WHERE ticket_id = %s ORDER BY id", (ticket_id,)
                    )
                ).fetchall()
            mine = [d for d in decisions.get("decisions", []) if d.get("user_id") == t["user_id"]]
            reconstruction = {"ticket": t, "events": events, "checkpoint_decisions_for_user": mine}

    async with state.pool.connection() as c:
        purges = await (await c.execute("SELECT * FROM purge_runs ORDER BY id DESC LIMIT 20")).fetchall()

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "inventory": {
            "atlas": inventory,
            "agents": [
                {
                    "id": a.id,
                    "tenant": a.tenant,
                    "model": a.model,
                    "skill": a.skill,
                    "skill_digest": digest(Path(cfg.skills_dir) / a.skill / "SKILL.md"),
                    "risk": roster.risk.get(a.id, {}),
                }
                for a in roster.agents.values()
            ],
        },
        "configuration": {
            "models": {"file": cfg.models_file, "digest": digest(cfg.models_file), "tiers": roster.models},
            "agents": {"file": cfg.agents_file, "digest": digest(cfg.agents_file)},
        },
        "oversight": {"checkpoint_decisions_by_tenant": counts, "ticket": reconstruction},
        "retention": {"days": cfg.retention_days, "recent_purges": purges},
        "disclosure": DISCLOSURE,
    }
