# ADR 0002: Automated checks are tripwires; a second person approves

Status: accepted (2026-10-15)

## Context
A skill can ship scripts an agent will run, an MCP server reaches into company systems, and an agent card points
traffic at an endpoint. Static analysis cannot prove any of these safe: a determined author can evade pattern
matching, and benign code can look suspicious.

## Decision
Every submission runs automated checks with three severities. `block` findings (piping a download to a shell,
hidden Unicode, committed secrets, compiled binaries, plain-HTTP endpoints, unauthenticated agents, unpinned MCPB
packages) reject the submission at once. Everything else goes to a human reviewer, who must explicitly acknowledge
`warn` findings before approving. The reviewer cannot be the submitter. When `ATLAS_EVAL_MIN_SCORE` is set, approval
also needs an eval report at or above it.

## Consequences
+ Cheap, fast rejection of the obviously dangerous; human judgement for everything that reaches users.
+ The audit log shows who approved what and which warnings they accepted.
- Reviewers are a bottleneck; size the reviewer group to the publishing rate.
- A clean scan is not a guarantee. Runtime controls still apply: the MCP gateway (Checkpoint) enforces policy on
  every tool call, and agents run skills in sandboxes.
