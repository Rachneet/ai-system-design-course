# ADR 0001: Cedar for tool policy, with approvals as annotations

Status: accepted (2026-10-15)

## Context
Every tool call needs a decision from the agent, the tool, the arguments and the user: allow, deny, or allow only
after a person approves. The rules change more often than the code and are read by security reviewers, not only
engineers. Hand-written `if` statements spread these rules across services and cannot be analysed.

## Decision
Policies are Cedar, evaluated in process with `cedarpy` (the Rust engine). Agents are principals, tools
(`server__tool`) are resources, `list` and `call` are actions, and the context carries the arguments, the verified
user and the server. Cedar denies by default and any matching `forbid` wins. A `permit` annotated
`@approval("required")` allows a call only after an approval for exactly that agent, user, tool and arguments; the
approval is single use. Decisions record the `@id` of the policies that produced them.

## Consequences
+ The rules live in one reviewable file, with deny-by-default and forbid-wins semantics security teams expect.
+ AWS Bedrock AgentCore Policy describes its rules as Cedar-compatible, so the skill transfers.
- `cedarpy` is a community binding; pin it and watch for releases. The engine itself is Amazon's Cedar.
- Arguments are free-form JSON, so policies are not schema-validated yet; a per-tool Cedar schema is a next step.
