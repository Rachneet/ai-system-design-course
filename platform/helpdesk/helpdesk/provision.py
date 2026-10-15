"""Provision Helpdesk OS on the platform, through each service's admin API, for one environment.

Switchboard   an org per tenant, a team per agent, an app per agent and environment (only that agent's model,
              a monthly budget), and a key per app
Atlas         a platform team; every MCP server with its pinned tool list, every agent card and every skill,
              published by one principal and approved by another; a reader token for Checkpoint
Checkpoint    a tenant-bound identity per agent, and a console approver per tenant

Prints the secrets Helpdesk needs as environment variables (HELPDESK_AGENTS, HELPDESK_CONSOLE_TOKENS) and the
token Checkpoint uses to read Atlas. Run it once per environment (production, staging, evals):

    uv run python -m helpdesk.provision --env staging > .env.staging
"""

import argparse
import asyncio
import io
import json
import os
import sys
import zipfile
from pathlib import Path

import httpx

from .roster import Roster, load
from .servers.systems import Store, all_servers

VERSION = "1.0.0"
TEAM = "helpdesk-platform"


class ProvisionError(RuntimeError):
    pass


def ok(resp: httpx.Response, *allowed: int) -> dict:
    if resp.status_code not in (allowed or (200, 201)):
        raise ProvisionError(f"{resp.request.method} {resp.request.url.path}: {resp.status_code} {resp.text[:300]}")
    return resp.json() if resp.content else {}


def accepted(resp: httpx.Response, name: str) -> None:
    """Published (or already there). Atlas's blocking checks reject at once; provisioning must not carry on."""
    if ok(resp, 201, 409).get("status") == "rejected":
        raise ProvisionError(f"Atlas rejected {name}: {resp.json().get('review_note')}")


def agent_card(spec, base_url: str) -> dict:
    """Registry entry for review and inventory. Handoffs run in-process (ADR 0001), so the interface is Helpdesk's
    ticket API rather than a public A2A endpoint."""
    return {
        "name": spec.id,
        "description": spec.description,
        "version": VERSION,
        "supportedInterfaces": [
            {"url": f"{base_url}/v1/tickets", "protocolBinding": "HTTP+JSON", "protocolVersion": "1.0"}
        ],
        "capabilities": {"streaming": False},
        "securitySchemes": {"user": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [{"id": spec.skill, "name": spec.skill, "description": spec.description, "tags": [spec.tenant]}],
    }


def skill_zip(skills_dir: str, name: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted((Path(skills_dir) / name).rglob("*")):
            if path.is_file():
                z.writestr(f"{name}/{path.relative_to(Path(skills_dir) / name)}", path.read_bytes())
    return buf.getvalue()


async def switchboard(sb: httpx.AsyncClient, roster: Roster, env: str, budget_usd: float) -> dict[str, str]:
    for tenant, t in roster.tenants.items():
        ok(await sb.post("/admin/orgs", json={"id": tenant, "name": t["name"]}), 201, 409)
    keys = {}
    for a in roster.agents.values():
        ok(await sb.post("/admin/teams", json={"id": a.id, "org_id": a.tenant, "name": a.id}), 201, 409)
        app = f"{a.id}-{env}"
        policy = {"allowed_models": [a.model], "budget_usd_month": budget_usd, "pii_mode": "detect"}
        ok(await sb.post("/admin/apps", json={"id": app, "team_id": a.id, "name": app} | policy), 201, 409)
        keys[a.id] = ok(await sb.post(f"/admin/apps/{app}/keys", json={"label": "provisioned"}), 201)["key"]
    return keys


async def atlas(at: httpx.AsyncClient, roster: Roster, skills_dir: str, systems_url: str, base_url: str) -> str:
    ok(await at.post("/admin/teams", json={"id": TEAM, "name": "Helpdesk platform"}), 201)
    principals = {}
    for label, team, roles in (("helpdesk-ci", TEAM, ["publisher"]), ("helpdesk-reviewer", None, ["reviewer"])):
        principals[label] = ok(
            await at.post("/admin/principals", json={"label": label, "team_id": team, "roles": roles})
        )
    reader = ok(await at.post("/admin/principals", json={"label": "checkpoint", "roles": ["reader"]}))["token"]
    pub = {"authorization": f"Bearer {principals['helpdesk-ci']['token']}"}
    rev = {"authorization": f"Bearer {principals['helpdesk-reviewer']['token']}"}

    published = []
    for segment, server in all_servers(Store()).items():
        doc = {
            "name": server.name,
            "description": f"Helpdesk OS {segment} system",
            "version": VERSION,
            "remotes": [{"type": "streamable-http", "url": f"{systems_url}/{segment}/mcp"}],
        }
        tools = [t.descriptor() for t in server.tools.values()]
        accepted(await at.post("/v1/mcp-servers", json={"server": doc, "tools": tools}, headers=pub), server.name)
        published.append(("mcp_server", server.name))
    for a in roster.agents.values():
        accepted(await at.post("/v1/agents", json={"id": a.id, "card": agent_card(a, base_url)}, headers=pub), a.id)
        published.append(("a2a_agent", a.id))
    for name in sorted({a.skill for a in roster.agents.values()}):
        files = {"package": (f"{name}.zip", skill_zip(skills_dir, name), "application/zip")}
        accepted(await at.post("/v1/skills", files=files, data={"version": VERSION}, headers=pub), name)
        published.append(("skill", name))
    for kind, name in published:
        review = {"decision": "approve", "acknowledge_warnings": True, "note": "provisioned for Helpdesk OS"}
        ok(await at.post(f"/v1/artifacts/{kind}/{name}/versions/{VERSION}/review", json=review, headers=rev), 200, 409)
    return reader


async def checkpoint(cp: httpx.AsyncClient, roster: Roster) -> tuple[dict[str, str], dict[str, str]]:
    tokens = {}
    for a in roster.agents.values():
        tokens[a.id] = ok(await cp.post("/admin/agents", json={"id": a.id, "tenant": a.tenant}))["token"]
    consoles = {}
    for tenant in roster.tenants:
        body = {"id": f"{tenant}-console", "role": "approver", "tenant": tenant}
        consoles[tenant] = ok(await cp.post("/admin/agents", json=body))["token"]
    return tokens, consoles


async def provision(
    sb: httpx.AsyncClient,
    at: httpx.AsyncClient,
    cp: httpx.AsyncClient,
    roster: Roster,
    *,
    env: str,
    skills_dir: str,
    systems_url: str,
    base_url: str,
    budget_usd: float = 200.0,
) -> dict:
    """Clients carry each service's admin token. Returns everything Helpdesk and Checkpoint need."""
    keys = await switchboard(sb, roster, env, budget_usd)
    reader = await atlas(at, roster, skills_dir, systems_url, base_url)
    tokens, consoles = await checkpoint(cp, roster)
    agents = {a: {"switchboard_key": keys[a], "checkpoint_token": tokens[a]} for a in roster.agents}
    return {"agents": agents, "console_tokens": consoles, "atlas_reader_token": reader}


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--env", default="staging", choices=["production", "staging", "evals"])
    p.add_argument("--budget-usd", type=float, default=200.0, help="monthly budget per agent app")
    p.add_argument("--systems-url", default=os.environ.get("HELPDESK_SYSTEMS_URL", "https://systems.helpdesk.internal"))
    p.add_argument("--base-url", default=os.environ.get("HELPDESK_BASE_URL", "https://helpdesk.internal"))
    args = p.parse_args()
    env = os.environ

    def client(url_var: str, token_var: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=env[url_var], headers={"authorization": f"Bearer {env[token_var]}"}, timeout=30
        )

    roster = load(
        env.get("HELPDESK_AGENTS_FILE", "config/agents.toml"),
        env.get("HELPDESK_MODELS_FILE", "config/models.toml"),
        "skills",
    )
    async with (
        client("SWITCHBOARD_URL", "SWITCHBOARD_ADMIN_TOKEN") as sb,
        client("ATLAS_URL", "ATLAS_ADMIN_TOKEN") as at,
        client("CHECKPOINT_URL", "CHECKPOINT_ADMIN_TOKEN") as cp,
    ):
        out = await provision(
            sb,
            at,
            cp,
            roster,
            env=args.env,
            skills_dir="skills",
            systems_url=args.systems_url,
            base_url=args.base_url,
            budget_usd=args.budget_usd,
        )
    print(f"HELPDESK_AGENTS='{json.dumps(out['agents'])}'")
    print(f"HELPDESK_CONSOLE_TOKENS='{json.dumps(out['console_tokens'])}'")
    print(f"# for Checkpoint: CHECKPOINT_ATLAS_TOKEN={out['atlas_reader_token']}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
