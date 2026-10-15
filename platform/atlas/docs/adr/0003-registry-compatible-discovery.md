# ADR 0003: Discovery in the formats clients already speak; upstream never auto-approves

Status: accepted (2026-10-15)

## Context
MCP clients know the official registry API, A2A clients fetch agent cards, and skill loaders want a zip. A custom
discovery format would need a client change everywhere. The public MCP registry lists thousands of servers, but its
listing says a server exists, not that this organisation trusts it.

## Decision
- `GET /v0/servers` returns approved MCP servers in the official registry response shape (`servers[].server`,
  `metadata.nextCursor`), adding review data under `_meta["io.atlas/review"]` (status, owner, digest, reviewer).
- `GET /v1/agents/{id}/agent-card.json` serves the latest approved agent card; `GET /v1/skills/{name}/{version}.zip`
  serves the exact approved bytes, with the sha256 in `x-atlas-digest` and the ETag.
- `POST /admin/sync/mcp` imports from the public registry into review with `source = upstream` and no owning team.
  The same checks run; nothing imported is ever approved automatically.

## Consequences
+ Pointing an MCP client at Atlas instead of the public registry gives it a curated sub-registry with no code change.
+ Clients can pin by digest and detect any change.
- The `/v0/servers` cursor is opaque and Atlas-specific; clients must not parse it.
