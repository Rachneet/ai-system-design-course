# Checkpoint: the MCP gateway with policy

The control point every agent tool call passes through. Agents connect to one MCP endpoint; Checkpoint shows them
only the tools of servers approved in [Atlas](../atlas) that policy lets them see, decides every call with Cedar,
holds risky calls for a person, calls the server with a signed assertion naming the user and the agent, and scans
what comes back. Part of the enterprise track of the [AI System Design Course](../../README.md).

## What it does

| Concern | How |
|---|---|
| Protocol | MCP 2026-07-28 (stateless) to agents, with every mirrored header checked against the body; modern and initialize-era servers upstream |
| Catalog | Only Atlas-approved servers on HTTPS; tools namespaced `server__tool`; refreshed on a TTL |
| Agent identity | Each agent has its own token; approvers have separate tokens and cannot call tools |
| User identity | The user's JWT (`X-User-Token`), verified with a shared secret in development or your IdP's JWKS |
| Policy | Cedar: default deny, forbid wins, decisions name their policies; `@approval("required")` holds a call for a person; a forbid that fails to evaluate denies, and evaluation errors are logged |
| Approvals | Bound to agent, user, tool and exact arguments; single use; pending requests lapse after 30 minutes and approvals after 5 (`APPROVAL_PENDING_TTL_S`, `APPROVAL_USE_TTL_S`); nobody decides a request made on their own behalf; approver API |
| Upstream identity | RS256 assertion (`sub` user, `act.sub` agent, `aud` server, 60 s) verifiable at `/.well-known/jwks.json`; server credentials stay in Checkpoint |
| Output | Hidden Unicode removed, secrets redacted, instruction-like text marked as data, flags in `_meta` |
| Limits and audit | Per-agent, per-tool rate limits; every decision logged; Prometheus metrics |

```mermaid
sequenceDiagram
  participant Agent
  participant CP as Checkpoint
  participant Atlas
  participant Srv as MCP server
  Agent->>CP: tools/call payments__refund (agent token, user JWT)
  CP->>Atlas: approved servers (cached)
  CP->>CP: headers = body? Cedar: allow, deny or hold
  alt held for approval
    CP-->>Agent: isError, approval id
  else allowed
    CP->>Srv: tools/call refund + signed assertion (user, agent)
    Srv-->>CP: result
    CP->>CP: scan output, log decision
    CP-->>Agent: result
  end
```

## Policies

`policies/default.cedar` shows the patterns. A sketch:

```cedar
@id("refunds-small")
permit(principal == Agent::"refunds", action == Action::"call", resource == Tool::"payments__refund")
when { context.user.roles.contains("support") && context.args.amount <= 200 };

@id("refunds-large-need-approval")
@approval("required")
permit(principal == Agent::"refunds", action == Action::"call", resource == Tool::"payments__refund")
when { context.user.roles.contains("support") && context.args.amount > 200 && context.args.amount <= 2000 };

@id("no-self-refund")
forbid(principal, action == Action::"call", resource == Tool::"payments__refund")
when { context.args has customer_id && context.args.customer_id == context.user.id };
```

Edit the file and `POST /admin/policy/reload`; a file that does not parse is refused and the running policy stays.

## Run it

```bash
uv sync
export CHECKPOINT_DATABASE_URL=postgresql://postgres:checkpoint@localhost:5432/checkpoint
uv run alembic upgrade head
CHECKPOINT_ADMIN_TOKEN=... CHECKPOINT_ATLAS_URL=https://atlas.internal CHECKPOINT_ATLAS_TOKEN=atk_... \
CHECKPOINT_USER_JWKS_URL=https://idp.example/.well-known/jwks.json CHECKPOINT_ASSERTION_PRIVATE_KEY="$(cat key.pem)" \
uv run uvicorn checkpoint.main:app

curl -X POST localhost:8000/admin/agents -H "Authorization: Bearer $ADMIN" -H 'content-type: application/json' -d '{"id":"refunds"}'
curl -X POST localhost:8000/admin/agents -H "Authorization: Bearer $ADMIN" -H 'content-type: application/json' -d '{"id":"finance-lead","role":"approver"}'
```

Point an MCP client (any SDK on protocol 2026-07-28) at `http://localhost:8000/mcp` with the agent token as a
bearer token and the user's JWT in `X-User-Token`. Approvers use `GET /approvals` and
`POST /approvals/{id}/decision`.

## Tests

`uv run pytest` runs 13 tests (9 end to end, 3 policy unit tests and a migration round trip) against a real Postgres, a mock Atlas, a modern MCP server and an
initialize-era one: transport rules, catalog filtering, assertions verified against the published JWKS, Cedar
denials with reasons, forbids that fail closed when they cannot evaluate, single-use approvals bound to arguments that expire, output scanning, `x-mcp-header` handling in both
directions, rate limits, forged user tokens, the decision log and refusal of a broken policy file. CI adds ruff,
bandit, pip-audit, an image build with Trivy and an SBOM, and a container smoke test.

## Engineering docs

- [ADR 0001](docs/adr/0001-cedar-policy-with-approval-annotations.md): Cedar, with approvals as annotations
- [ADR 0002](docs/adr/0002-signed-assertions-not-shared-credentials.md): signed assertions, not shared credentials
- [ADR 0003](docs/adr/0003-mcp-2026-07-28-with-legacy-fallback.md): MCP 2026-07-28, with a fallback for older servers
- [Threat model](docs/THREAT_MODEL.md) and [security policy](SECURITY.md)

## Not built yet

Proxying resources, prompts and `subscriptions/listen`; per-tool Cedar schemas; OAuth token exchange at the IdP;
tool search to keep large catalogs out of context; shared rate limits; SSO for approvers.
