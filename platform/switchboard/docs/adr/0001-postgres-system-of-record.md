# ADR 0001: Postgres as the system of record

Status: accepted (2026-10-15)

## Context
Switchboard stores tenancy (orgs, teams, apps), hashed keys, an append-only usage ledger, monthly spend, audit
bodies and the admin audit log. Chargeback must reconcile to the provider invoice, and teams already run Postgres.

## Decision
Postgres 16 for everything durable, schema managed by Alembic migrations (plain SQL), never created at startup.

## Consequences
+ One datastore to operate, back up and secure; transactions keep the ledger and totals consistent.
- Postgres must not sit on the per-request hot path for shared counters (see ADR 0002).
- Revisit if usage events exceed roughly 50M rows a month: partition `usage_events` by month and move analytics
  to a warehouse.
