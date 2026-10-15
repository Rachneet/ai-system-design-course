# Helpdesk OS: a multi-tenant support platform on Switchboard, Atlas and Checkpoint

The reference implementation of the course's [enterprise capstone](../../content/10-04-capstone.md). There are two tenants that
must never see each other's data: an **employee desk** (IT access and HR policy) and a **customer desk** (billing and
returns). Six agents resolve tickets end to end. Every model call goes through [Switchboard](../switchboard), and
every tool call through [Checkpoint](../checkpoint). Every MCP server, agent card and skill is approved in
[Atlas](../atlas) before anything runs. Part of the enterprise track of the [AI System Design Course](../../README.md).

```mermaid
flowchart LR
  E[Employees, company SSO] --> HD
  C[Customers, store sign-in] --> HD
  subgraph HD[Helpdesk OS]
    T1[emp-triage] --> IT[it-access] & HR[hr-policy]
    T2[cust-triage] --> B[billing] & R[returns]
    CON[Console: approvals, escalations, kill switches, traces]
  end
  HD -->|agent key, ticket tag| SB[Switchboard] --> P[Any model provider]
  HD -->|agent token + user JWT| CP[Checkpoint] -->|signed assertion| S[IdP, KB, orders, ticketing MCP servers]
  CP -->|approved servers, pinned tools| AT[Atlas]
```

## What it shows

| Brief component | How Helpdesk OS does it |
|---|---|
| Tenancy | Switchboard org per tenant, team per agent, app per agent and environment. Checkpoint agents bound to a tenant. Forced row-level security on every tenant table, with the app connecting as a role without `BYPASSRLS`. Each system scopes data by the tenant in Checkpoint's assertion |
| Agents | Two triage agents and four specialists in [`config/agents.toml`](config/agents.toml). Instructions live in Agent Skills packages ([`skills/`](skills)). Every model choice is in [`config/models.toml`](config/models.toml) |
| Handoffs | A typed `handoff(to, summary)` with targets fixed per agent. At most 3 per ticket, never back to a visited agent; anything else goes to a person ([ADR 0001](docs/adr/0001-typed-in-process-handoffs.md)) |
| MCP servers | Identity provider, knowledge bases, orders and billing, and ticketing, as MCP 2026-07-28 servers that trust only Checkpoint's RS256 assertion and check ownership themselves |
| Policy | [`policies/helpdesk.cedar`](policies/helpdesk.cedar): own-account unlocks; approval for sensitive groups and for refunds from 50 to 500 EUR; nothing above 500; a read-only HR agent; tool-less triage; a wall around each tenant's systems |
| Human console | Approval queue (decided in Checkpoint on behalf of the signed-in person, never by the requester), escalation queue with summary and trace link, kill switch per agent |
| Identity | User JWTs with a `tenant` claim, verified by Helpdesk and again by Checkpoint ([ADR 0003](docs/adr/0003-one-user-token-two-audiences.md)) |
| Observability | One trace id per ticket, sent as `traceparent` to Switchboard and Checkpoint. Every model call (with Switchboard's request id), tool call (with Checkpoint's outcome), handoff, approval and escalation is stored, so `GET /console/tickets/{id}/trace` reconstructs it. Prometheus metrics, JSON logs |
| Evals | Behavioural suites per agent and for handoffs, gated with pass^k and must-never categories. Red-team and cross-tenant suites that assume a compromised model, run in CI |
| FinOps | Each model call is tagged `ticket:<id>:<agent>` in Switchboard's ledger. `GET /admin/finops` gives cost per resolved ticket per tenant and agent, with people's time added at labelled assumed costs. Budgets degrade a desk to people, never to an error |
| Governance | `GET /admin/evidence`: inventory from Atlas, risk assessment per agent, configuration digests, Checkpoint decisions, a reconstructed ticket, retention settings and purge history, the AI disclosure. Both front ends disclose the AI, and a test checks it |

## Run it

Start Switchboard, Atlas and Checkpoint as their READMEs describe. Then give Checkpoint this policy, and require pinned
tool lists:

```bash
CHECKPOINT_POLICY_FILE=../helpdesk/policies/helpdesk.cedar CHECKPOINT_REQUIRE_PINNED_TOOLS=true \
CHECKPOINT_USER_JWT_SECRET=$USER_SECRET ... uv run uvicorn checkpoint.main:app --port 8002
```

Run Helpdesk's systems of record, provision the platform, then start Helpdesk:

```bash
cd platform/helpdesk && uv sync
HELPDESK_SYSTEMS_CHECKPOINT_JWKS_URL=http://localhost:8002/.well-known/jwks.json \
  uv run uvicorn helpdesk.servers.main:app --port 8443        # behind TLS: Checkpoint reaches servers over HTTPS only

SWITCHBOARD_URL=... SWITCHBOARD_ADMIN_TOKEN=... ATLAS_URL=... ATLAS_ADMIN_TOKEN=... CHECKPOINT_URL=... CHECKPOINT_ADMIN_TOKEN=... \
  uv run python -m helpdesk.provision --env staging --systems-url https://systems.example --base-url https://helpdesk.example > .env

psql -c "CREATE ROLE helpdesk_app LOGIN PASSWORD '...'"         # no superuser, no BYPASSRLS
HELPDESK_DATABASE_URL=postgresql://postgres:...@localhost/helpdesk uv run alembic upgrade head
HELPDESK_DATABASE_URL=postgresql://helpdesk_app:...@localhost/helpdesk HELPDESK_USER_JWT_SECRET=$USER_SECRET \
HELPDESK_DEV_TOKENS=true uv run uvicorn helpdesk.main:app --port 8080
```

Switchboard needs the two model names from `config/models.toml` in `SWITCHBOARD_CHAT_MODELS`, mapped to any provider.
Open `http://localhost:8080/` (customer desk) or `/staff` (employee desk). In development, get a token with
`POST /dev/token {"sub": "e-ada", "tenant": "employee"}`. Console calls need `approver` or `supervisor` in the token's roles.

## Tests

`uv run pytest` runs 73 tests in about 25 seconds, with no Docker and no model key. They start the **real** Switchboard,
Atlas and Checkpoint in process, each on its own schema of one embedded Postgres, together with the MCP servers and
Helpdesk. They provision everything through the admin APIs, exactly as `helpdesk.provision` does in production. Only
the model provider is scripted.

- **Policy** (25): Checkpoint's own Cedar engine over `helpdesk.cedar`. The HR agent reaches no write tool for any
  arguments, with the write tools enumerated from the servers' `readOnlyHint` annotations.
- **Platform** (10): an account unlock end to end, with no keys in agents and every call in the decision log. A
  refund held, refused to its requester, approved by a second person and run once. Cross-tenant attempts.
  Row-level security. Handoff refusal. The kill switch. A spent budget. Cost per resolved ticket. The evidence pack and
  disclosure.
- **Red-team** (34): per tenant and cross-tenant, with the model fully compromised; see
  [`evals/redteam`](evals/redteam). A deliberately weakened policy fails them.
- **Evals** (3) and a migration round trip (1).

The behavioural suites in [`evals/cases`](evals/cases) (36 cases) measure a real model and run against a deployed
evals environment with `python -m helpdesk.evals`. CI runs them when `HELPDESK_EVAL_BASE_URL` is set. The brief asks
learners for 40 to 50 cases per agent; these are the starting set, not the target.

## Engineering docs

- [Design](docs/DESIGN.md): context and containers, tenancy model, SLOs and the cost model
- [ADR 0001](docs/adr/0001-typed-in-process-handoffs.md): typed in-process handoffs, not A2A between processes
- [ADR 0002](docs/adr/0002-run-approved-calls-with-the-stored-user-token.md): run approved calls with the requester's stored token
- [ADR 0003](docs/adr/0003-one-user-token-two-audiences.md): one user token for Helpdesk and Checkpoint
- [ADR 0004](docs/adr/0004-red-team-assumes-a-compromised-model.md): red-team with a compromised model
- [Threat model](docs/THREAT_MODEL.md) and [security policy](SECURITY.md)

## Not built yet

Real SSO (OIDC login flows; tokens are verified, not obtained). OAuth token exchange instead of a two-audience token.
A2A over the network between agents. Streaming replies. Load tests and the SLO dashboards (the SLOs are defined in the
design doc, not yet measured). Alert rules with runbooks. Per-tenant knowledge base retrieval with embeddings (the
knowledge bases use keyword search). OpenTofu deployment.
