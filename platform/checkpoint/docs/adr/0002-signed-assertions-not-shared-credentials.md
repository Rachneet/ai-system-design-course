# ADR 0002: Upstream servers get a signed assertion, never the agent's credentials

Status: accepted (2026-10-15)

## Context
An MCP server needs to know which user an action is for and which agent is asking, for its own authorization and
audit. Passing the agent's token upstream would let any server replay it against every other server. Passing the
user's token lets a server act as the user anywhere that token is accepted.

## Decision
Checkpoint verifies the user's JWT (X-User-Token) and the agent's token, then sends the upstream server a
short-lived RS256 assertion it signs itself: `sub` is the user, `act.sub` the agent (the RFC 8693 actor claim),
`aud` the server, plus the tool, a 60-second expiry and a unique `jti`. Servers verify it against
`/.well-known/jwks.json`. The server's own service credential, if any, is configured in Checkpoint and sent as
`Authorization`; agents never see it.

## Consequences
+ A leaked assertion is useful for one server, for one minute.
+ Servers see both identities without trusting plain headers.
- Servers must verify assertions; until they do, run them on a network only Checkpoint can reach.
- A full OAuth token exchange with the identity provider (RFC 8693 at the IdP) is the production upgrade, so the
  IdP, not Checkpoint, issues the downstream token.
