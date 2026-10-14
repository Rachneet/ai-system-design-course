# Switchboard: an AI gateway

One endpoint between every internal app and the model provider. Apps call Switchboard exactly as they would call the
Anthropic Messages API (same request, same streaming events, same error shape), with a Switchboard key instead of a
provider key. Part of the enterprise track of the [AI System Design Course](../../README.md).

## What it does

| Concern | How |
|---|---|
| Identity | Per-app keys `sbk_<id>_<secret>`; only a SHA-256 is stored; expiry and instant revocation |
| Tenancy | org → team → app, each with an optional monthly budget |
| Policy | Allowed models per app, enforced on fallbacks too; allow-listed `anthropic-beta` headers |
| Cost and abuse limits | Requests and tokens per minute per app; monthly budgets at every level |
| Reliability | Timeouts, circuit breakers, fallback chains tried before the first byte reaches the client |
| Personal data | `pii_mode`: off, detect (count only) or redact (cards with Luhn, emails, phones, IBANs) |
| Prompt caching | Request bytes are forwarded unchanged unless policy must change them ([ADR 0003](docs/adr/0003-forward-bytes-unchanged.md)) |
| Metering | Append-only usage ledger, monthly totals, chargeback report by org, team, app or model |
| Audit | Admin actions logged; request and response bodies only on opt-in, always redacted, with expiry |
| Operations | Prometheus metrics, OpenTelemetry spans, JSON logs, `Server-Timing` header, health and readiness |

```mermaid
flowchart LR
  A[Internal apps] -->|sbk_ key| SB[Switchboard]
  SB -->|keys cached, limits in memory| SB
  SB -->|provider key| P[Model provider]
  SB -. batched every 0.5 s .-> DB[(Postgres: tenancy, ledger, spend, audit)]
  OPS[Admin / FinOps] -->|/admin| SB
```

## Run it

```bash
uv sync
export SWITCHBOARD_DATABASE_URL=postgresql://postgres:switchboard@localhost:5432/switchboard
uv run alembic upgrade head
SWITCHBOARD_ADMIN_TOKEN=... SWITCHBOARD_ANTHROPIC_API_KEY=... uv run uvicorn switchboard.main:app
```

Provision with the admin API (`POST /admin/orgs`, `/admin/teams`, `/admin/apps`, `/admin/apps/{id}/keys`), then point
any Anthropic SDK at it:

```python
import anthropic

client = anthropic.Anthropic(base_url="http://localhost:8000", api_key="sbk_...")
```

Chargeback: `GET /admin/usage?month=2026-10&group_by=team`.

## Tests and measurements

```bash
uv run pytest                                   # 27 tests on an embedded Postgres; no provider key needed
uv run python -m loadtest.overhead --concurrency 32
```

| Gateway time per request (inside the handler, laptop, single process) | p50 | p95 | p99 |
|---|---|---|---|
| v0.1: shared Postgres buckets, per-request ledger writes, concurrency 32 | 54.1 ms | 63.9 ms | 67.7 ms |
| v0.2: local limits, batched ledger, cached budgets, concurrency 32 | <0.1 ms | 0.1 ms | 1.0 ms |

The v0.1 numbers came from row-lock contention, found by sampling `pg_stat_activity` under load. The fix and its
trade-offs are in [ADR 0002](docs/adr/0002-local-rate-limits-batched-ledger.md), including what this load test
cannot show (the mock provider shares the CPU, so end-to-end capacity needs separate hardware).

## Engineering docs

- [Threat model (STRIDE)](docs/THREAT_MODEL.md), with the test or control behind each mitigation
- [ADR 0001](docs/adr/0001-postgres-system-of-record.md) Postgres as the system of record
- [ADR 0002](docs/adr/0002-local-rate-limits-batched-ledger.md) per-instance limits and a batched ledger
- [ADR 0003](docs/adr/0003-forward-bytes-unchanged.md) forward bytes unchanged
- [SECURITY.md](SECURITY.md) disclosure policy
- CI: lint, tests, Bandit, pip-audit, image build, Trivy scan, SBOM, container smoke test

## Not built yet

OpenAI-compatible endpoint; per-tenant data-residency routing; Redis-backed exact global limits; SSO for `/admin`;
signed images (cosign); OpenTofu deployment. Each is a planned follow-up in `docs/enterprise-track.md`.
