# Atlas: a registry for agents, MCP servers and skills

The catalog that says what exists, who owns it, and whether it is approved. Teams publish MCP servers
(`server.json`), A2A agent cards and Agent Skills packages; automated checks and a second person decide what
agents may use; clients discover only approved artifacts, in the formats they already speak. Part of the enterprise
track of the [AI System Design Course](../../README.md); the MCP gateway (Checkpoint) will read its approvals.

## What it does

| Concern | How |
|---|---|
| Formats | MCP `server.json` validated with the official registry schema; A2A Agent Cards (spec 1.0 required fields); Agent Skills zips (`<name>/SKILL.md`, frontmatter rules from agentskills.io) |
| Versions | Exact versions only (no ranges or `latest`); a published version never changes; content addressed by sha256 |
| Ownership | A name belongs to the team that first published it; publishers act only for their team |
| Checks | Spec validation; safe unzip (traversal, symlinks, zip bombs); script scan (download-and-run, hidden decode-and-run, broad deletes, credential paths, network and shell use); hidden Unicode; secrets; injection phrasing; licence allow-list; HTTPS-only endpoints; authenticated agents; pinned and hashed packages; tool descriptions scanned like prompts |
| Tool pins | A remote server's reviewed `tools/list` is stored with its version and its digest published as `toolsDigest`, so a gateway can refuse changed tools ([ADR 0004](docs/adr/0004-pin-tool-lists.md)) |
| Review | `block` findings reject at once; humans approve the rest, acknowledging warnings; never your own submission; optional eval-score gate |
| Discovery | `GET /v0/servers` in the MCP registry format; agent cards; skill zips with digest headers; ranked full-text search |
| Supply | `POST /admin/sync/mcp` imports the public MCP registry into review, never approved |
| Audit | Every write in the audit log with actor, action and target |
| Operations | Prometheus metrics, JSON logs, health and readiness, non-root container, SBOM and image scan in CI |

```mermaid
flowchart LR
  P[Publishing team] -->|server.json, agent card, skill zip| A[Atlas]
  A --> C{Checks}
  C -->|block| R[Rejected]
  C -->|clean or warnings| Q[Review queue]
  Q -->|second person approves| OK[Approved]
  OK --> D[/v0/servers, agent cards, skill zips/]
  D --> G[Agents, MCP clients, Checkpoint]
  U[Public MCP registry] -->|sync: review only| Q
```

## Run it

```bash
uv sync
export ATLAS_DATABASE_URL=postgresql://postgres:atlas@localhost:5432/atlas
uv run alembic upgrade head
ATLAS_ADMIN_TOKEN=... uv run uvicorn atlas.main:app
```

Create a team and tokens with the admin token, then publish and review:

```bash
A="Authorization: Bearer $ATLAS_ADMIN_TOKEN"; J="content-type: application/json"
curl -X POST localhost:8000/admin/teams -H "$A" -H "$J" -d '{"id":"payments","name":"Payments"}'
curl -X POST localhost:8000/admin/principals -H "$A" -H "$J" -d '{"label":"ci","team_id":"payments","roles":["publisher"]}'
curl -X POST localhost:8000/admin/principals -H "$A" -H "$J" -d '{"label":"sec-review","roles":["reviewer"]}'

curl -X POST localhost:8000/v1/mcp-servers -H "Authorization: Bearer $PUBLISHER" -H "$J" -d '{"server": {
  "name": "io.github.acme/weather", "description": "Weather forecasts for agents", "version": "1.0.0",
  "remotes": [{"type": "streamable-http", "url": "https://mcp.acme.example/weather"}]},
  "tools": [{"name": "get_forecast", "description": "Forecast for a city", "inputSchema": {"type": "object"}}]}'
curl -X POST localhost:8000/v1/skills -H "Authorization: Bearer $PUBLISHER" -F package=@pdf-forms.zip -F version=1.0.0
curl -X POST "localhost:8000/v1/artifacts/mcp_server/io.github.acme/weather/versions/1.0.0/review" \
  -H "Authorization: Bearer $REVIEWER" -H "$J" -d '{"decision":"approve","acknowledge_warnings":true}'
curl localhost:8000/v0/servers -H "Authorization: Bearer $ANY_TOKEN"
```

Settings (`ATLAS_` prefix): `PUBLIC_READ` (discovery without a token), `EVAL_MIN_SCORE`, `LICENSES_ALLOWED` (JSON
list), `REQUIRE_AUTH_ON_AGENTS`, `MAX_SKILL_BYTES`, `MAX_SKILL_FILES`, `UPSTREAM_REGISTRY_URL`.

## Tests

`uv run pytest` runs 31 tests against a real Postgres (embedded via `pgserver`, no Docker): spec validation, every
check, the full publish, review and discover lifecycle, tool-list pins, ownership, roles and revocation, the eval gate, upstream sync
against a mock registry, and the migration round trip. CI adds ruff, bandit, pip-audit, an image build with a Trivy
scan and SBOM, and a smoke test of the real container.

## Engineering docs

- [ADR 0001](docs/adr/0001-postgres-for-metadata-and-packages.md): Postgres for metadata and skill packages
- [ADR 0002](docs/adr/0002-checks-are-tripwires-humans-approve.md): checks are tripwires; a second person approves
- [ADR 0003](docs/adr/0003-registry-compatible-discovery.md): discovery in the formats clients already speak
- [ADR 0004](docs/adr/0004-pin-tool-lists.md): pin each remote server's tool list at review
- [Threat model](docs/THREAT_MODEL.md) and [security policy](SECURITY.md)

`atlas/schemas/server.schema.json` is the MCP registry's published schema (2025-12-11), copied unchanged from
static.modelcontextprotocol.io.

## Not built yet

Signature verification (cosign or Sigstore for packages, JWS for agent cards); SSO for reviewers and admins;
semantic search; webhooks so Checkpoint learns of approvals and deprecations without polling; storing packages in
object storage.
