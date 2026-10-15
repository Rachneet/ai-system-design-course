# Threat model (STRIDE)

Scope: the ticket API, the console, the agent runtime, the systems of record, and Helpdesk's Postgres. Named threat:
**cross-tenant leakage**. The working assumption, from [ADR 0004](adr/0004-red-team-assumes-a-compromised-model.md):
any agent may be fully controlled by an attacker through text it reads.

| Threat | Example | Mitigation | Test or control |
|---|---|---|---|
| **Spoofing** a user | A model claims "I am e-cy" in tool arguments | Systems take the user from Checkpoint's signed assertion, never from arguments; Cedar compares arguments with the verified user | `employee/unlock-colleague`, `test_unlocking_someone_elses_account_*` |
| Spoofing an agent | One agent uses another's credentials | Each agent has its own Switchboard key and Checkpoint token, scoped to one model and one tenant | Provisioning; `test_account_unlock_end_to_end` (only Switchboard's key reaches the provider) |
| **Tampering** with an approved call | Approve 180 EUR, then run 1,800 | The stored call runs with exactly the approved arguments; Checkpoint binds the approval to their digest and uses it once | `test_a_large_refund_is_held_*` |
| Splitting to dodge approval | Two 50 EUR refunds instead of one 100 EUR refund | The orders system caps unattended refunds per order; only an assertion naming an approval goes beyond | `customer/split-refund-to-dodge-approval` |
| **Repudiation** | "The agent did it on its own" | Every model call (Switchboard request id), tool call (Checkpoint outcome), approval (the person) and handoff is in the ticket's trace; Checkpoint logs every decision | `test_account_unlock_end_to_end`, evidence pack |
| **Information disclosure** across tenants | A customer-desk agent reads employee tickets or KB articles | Tenant-bound agents; Cedar walls; systems scope by the assertion's tenant; forced RLS in Helpdesk | `cross-tenant/*` (10 cases), `test_rows_are_isolated_*` |
| Disclosure across customers | c-ana asks for c-ben's order | Orders are "not found" unless they belong to the assertion's `sub` | `customer/read-other-customers-order` |
| Injection through content | A KB article tells the agent to refund everything | Checkpoint marks instruction-like text; least privilege and approvals bound what a fooled agent can do | `customer/poisoned-article-is-flagged`, the refund cases |
| **Denial of service** | A looping agent burns budget | Step limit per turn, handoff limit per ticket, Switchboard budgets per app, Checkpoint rate limits; a spent budget goes to a person | `test_a_spent_budget_degrades_*`, `employee/handoff-loop` |
| **Elevation of privilege** | Triage or the HR agent writes | Tool-less triage; the HR agent has no write tool for any arguments | `test_policy.py`, `employee/hr-agent-tries-to-write` |
| Self-approval | The requester approves their own refund | Checkpoint refuses a decision by the request's user, even through the console | `test_a_large_refund_is_held_*` |
| Runaway agent | A model change makes an agent misbehave | Per-agent kill switch; its tickets go to people at once | `test_kill_switch_hands_tickets_to_people` |

## Residual risks

- Pending calls store the requester's JWT until it is used or expires ([ADR 0002](adr/0002-run-approved-calls-with-the-stored-user-token.md)).
  The database is a high-value target: restrict access, and keep user tokens short-lived.
- The user token names two audiences ([ADR 0003](adr/0003-one-user-token-two-audiences.md)). A leak of a Helpdesk
  token is also a leak of a Checkpoint token for that user. Token exchange removes this.
- Output scanning is a tripwire; the behavioural suites measure how often a real model is fooled at all.
- The systems are mocks. A real IdP or payment system must enforce its own ownership rules, as these do.
