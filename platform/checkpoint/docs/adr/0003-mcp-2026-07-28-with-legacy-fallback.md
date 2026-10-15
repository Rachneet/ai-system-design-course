# ADR 0003: Speak MCP 2026-07-28 to agents; fall back for older servers

Status: accepted (2026-10-15)

## Context
MCP 2026-07-28 made the protocol stateless: every request carries its version and capabilities in `_meta`,
mirrored into `MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name` and `Mcp-Param-*` headers. A gateway that routes or
authorizes on headers while the server executes the body is open to mismatch attacks. Many deployed servers still
speak the initialize-era revisions with sessions.

## Decision
Agents must use 2026-07-28. Checkpoint validates every header against the body and rejects mismatches with 400 and
`HeaderMismatch` (-32020), unknown versions with `UnsupportedProtocolVersion` (-32022) and the supported list, and
GET or DELETE with 405. Towards upstream servers it sends modern requests, mirroring `x-mcp-header` parameters, and
detects initialize-era servers by the spec's rule (a 400 without a recognized modern error), then uses initialize
and `Mcp-Session-Id`, re-initializing once on a 404.

## Consequences
+ The value Checkpoint authorizes is the value the server executes.
+ Older servers keep working behind the gateway while agents use the current protocol.
- Agents on older revisions are not supported; put them on a current SDK.
- Subscriptions (`subscriptions/listen`), resources and prompts are not proxied yet; tools are.
