# ADR 0004: Evals from your own history, not a public leaderboard

Status: accepted (2026-10-15)

## Context
Public coding benchmarks decay. In February 2026 OpenAI stopped reporting SWE-bench Verified, citing tests that
reject correct fixes and evidence that models had seen the problems in training, and recommended SWE-bench Pro
instead. Whatever replaces it will age the same way, and none of them is your codebase.

## Decision
A task is a snapshot of a repository before a real fix, the issue text, and a hidden test that the fix made pass.
`foundry eval` copies the snapshot, runs the coder, adds the hidden test and scores it; several trials per task give
pass@1 and pass^k. A test proves each task is real: the hidden test fails before the fix and passes with the
reference fix. Build more tasks from merged bug fixes in your own history.

## Consequences
+ The score measures your agent on your code, and the tasks cannot have leaked into public training data.
- Building tasks takes effort, and a small suite has wide error bars. Add a task for every regression you find.
