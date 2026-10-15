# ADR 0004: Pin each remote MCP server's tool list at review

Status: accepted (2026-10-15)

## Context
For a remote MCP server, the `server.json` a reviewer approves says where the server lives, not what it tells
models. Tool names, descriptions and schemas arrive from `tools/list` at run time and go straight into an agent's
context. The MCP specification lets a server change its tool list at any time, so a server approved on Monday can
add an instruction to a tool description on Tuesday (a "rug pull") with no new review.

## Decision
- A publisher may submit the server's `tools/list` result with the version (`POST /v1/mcp-servers` with `tools`).
  Atlas validates it (names unique, `inputSchema` an object), scans every tool's text with the same hidden-Unicode,
  injection and secret checks as other prompt text, and stores it with the version.
- The pin is `sha256` over canonical JSON (keys sorted, `,` and `:` separators, ASCII escapes) of the tools sorted by
  name, each reduced to `name`, `title`, `description`, `inputSchema`, `outputSchema` and `annotations`. Icons and
  `_meta` are left out: they change how a client displays a tool, not what a model reads or may send.
- Discovery publishes it as `_meta["io.atlas/review"].toolsDigest`. Checkpoint computes the same digest over the live
  `tools/list` and refuses a server whose tools differ until a version with the new list is approved.
- Remote servers published without a tool list get an `info` finding; gateways decide whether to accept unpinned
  servers (Checkpoint's `REQUIRE_PINNED_TOOLS`).

## Consequences
+ A changed tool description is a new version with a new review, which is the point.
+ The digest is defined here, so any gateway can enforce it, not only Checkpoint.
- A server that legitimately changes tools needs a release and a review; servers that generate tools dynamically
  cannot be pinned this way and need a different control (per-call review or a narrower server).
- The publisher supplies the list; a server could serve different tools to Atlas's reviewer and to gateways. The
  gateway's comparison at run time is what catches that.
