# ADR 0003: Branch and wait by default

Status: accepted (2026-10-15)

## Context
Merging is where an agent's change becomes everyone's problem. Teams differ in how far they trust a pipeline: some
will auto-merge dependency bumps, and almost none should auto-merge a schema change.

## Decision
Every accepted change becomes a branch `foundry/<job>` with provenance trailers and a ledger record. It merges by
fast-forward only when `auto_merge` is on and the repository is clean; otherwise it waits for a person. Protected
paths never pass the gates, so changes to them always need a person.

## Consequences
+ By default a person is accountable for every merge, and the trailers make agent-written commits searchable.
- Throughput is bounded by review. Turn `auto_merge` on per repository, for the change types your evals cover.
