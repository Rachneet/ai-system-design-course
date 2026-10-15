# ADR 0003: One user token for Helpdesk and Checkpoint

Status: accepted (2026-10-15)

## Context
Helpdesk verifies the user to serve their tickets. Checkpoint must verify the same user independently, to evaluate
policy and to tell systems who the call is for. Forwarding a token whose audience is Helpdesk would be token
passthrough: Checkpoint would accept a token not meant for it.

## Decision
User tokens name both audiences (`aud: ["helpdesk", "checkpoint"]`). Helpdesk verifies it with audience `helpdesk`,
and Checkpoint with audience `checkpoint`. Both require `exp` and `sub`, and both read the `tenant` claim themselves.
Systems never see the user's token; they get Checkpoint's assertion.

## Consequences
+ Checkpoint never trusts Helpdesk's word about the user. A compromised runtime cannot invent a user.
- A leaked token works at both services. The proper fix is OAuth token exchange: Helpdesk exchanges the user's
  token for one whose audience is Checkpoint, acting for this agent. Revisit when the identity provider supports
  RFC 8693, which Checkpoint's README also lists as not built yet.
