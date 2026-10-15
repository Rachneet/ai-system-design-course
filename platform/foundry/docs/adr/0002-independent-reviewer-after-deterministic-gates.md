# ADR 0002: An independent reviewer, after deterministic gates

Status: accepted (2026-10-15)

## Context
A model reviewing a change is useful, and cheap to fool: shown the coder's reasoning, it tends to agree with it.
Deterministic checks (tests, size, protected paths) are exact, cheap and impossible to argue with.

## Decision
Gates run first, on the result in the workspace, not on what the agent reports. Only a change that passes every gate
is reviewed. The reviewer is a separate call, ideally to a different model, that sees only the issue and the diff,
has no tools, and must answer `{"approve": bool, "reasons": [...]}`; anything else counts as a refusal.

## Consequences
+ Review tokens are spent only on changes that could merge, and the reviewer judges the change, not the story.
- The reviewer cannot run code; it relies on the gates for that, and gates catch only what they test for.
