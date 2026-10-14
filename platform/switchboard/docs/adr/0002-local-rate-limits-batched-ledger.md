# ADR 0002: Per-instance rate limits and a batched ledger

Status: accepted (2026-10-15). Supersedes the shared Postgres token buckets in migration 0001.

## Context
Version 0.1 enforced rate limits with a Postgres token bucket per app and wrote four statements to the ledger
per request. A load test (`loadtest/overhead.py`, one laptop, single process) showed the gateway's own time growing
with concurrency, and sampling `pg_stat_activity` showed why: requests queued on row locks for the app's bucket row
(the most frequent wait) and the three `spend_monthly` rows.

| Gateway time inside the handler (Server-Timing) | p50 | p95 | p99 |
|---|---|---|---|
| v0.1, concurrency 8 | 8.3 ms | 18.6 ms | 30.9 ms |
| v0.1, concurrency 32 | 54.1 ms | 63.9 ms | 67.7 ms |
| v0.2, concurrency 8 | <0.1 ms | <0.1 ms | 0.1 ms |
| v0.2, concurrency 32 | <0.1 ms | 0.1 ms | 1.0 ms |

## Decision
1. **Rate limits are local.** Each instance keeps in-memory token buckets sized at `limit / live_instances`.
   Instances heartbeat into Postgres every 5 s; the count rebalances within one interval after scaling or a crash.
   This is the model of Envoy's local rate limiting.
2. **Ledger writes are batched.** Events queue in memory and flush every 0.5 s in one transaction. Spend is
   aggregated per scope, added only for rows the insert actually created (retries never double count), and
   updated in sorted scope order (no deadlocks between instances).
3. **Budget checks are cached** for 2 s per (org, team, app).

## Consequences
+ No shared row on the request path; per-request database work is zero once a key is cached.
- Limits are exact per instance but approximate globally: uneven load balancing lets a client get up to
  `limit / n` more on a busy instance. Acceptable for abuse and cost protection; budgets (money) stay global.
- A hard crash can lose up to 0.5 s of usage records. Graceful shutdown flushes. `switchboard_ledger_*` metrics
  expose batch sizes, failed flushes and drops.
- Budgets can be overshot by about 2 s of traffic plus in-flight requests.
- If exact global limits are required (for example, contractual per-tenant quotas), use Redis with atomic Lua
  scripts or a dedicated rate-limit service; keep the interface in `limits.py`.

## What the measurement does not show
End-to-end latency still rises above concurrency 32 in the load test because the single-process Python mock
provider and the gateway share one laptop CPU (the mock alone saturates near 600 requests/s). Gateway capacity
needs a test against a faster upstream stub on separate hardware; until then, run several gateway processes
(`uvicorn --workers N`) behind a load balancer.
