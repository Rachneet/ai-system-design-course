# Threat model (STRIDE)

Scope: the `/mcp` endpoint, approvals and admin APIs, the policy file, assertions sent upstream, and Postgres.
The gateway exists because agents read untrusted text: a prompt-injected agent will try to call whatever it can.

| Threat | Example | Mitigation | Test or control |
|---|---|---|---|
| **Spoofing** an agent | Stolen or guessed agent token | Random 256-bit secrets, hash only, instant revocation; approver tokens cannot call tools | `test_transport_rules_are_enforced` |
| Spoofing a user | Agent claims to act for an admin | User identity only from a verified JWT; forged tokens get 401 | `test_rate_limits_and_bad_user_tokens` |
| Crossing tenants | Tenant A's agent is handed a tenant B user's token, or B's approver browses A's queue | Tenant-bound agents refuse other tenants' users before policy; approvals, decisions and assertions carry the tenant; approvers see their tenant only | `test_tenant_bound_agents_act_only_for_their_tenant` |
| Spoofing Checkpoint to a server | A server accepts any caller | Signed assertion with audience and 60 s expiry; JWKS published | `test_allowed_call_reaches_a_legacy_server_with_a_verifiable_assertion` |
| **Tampering** in transit | Header says one tool, body calls another | Every mirrored header checked against the body | `test_transport_rules_are_enforced`, `test_tool_output_is_scanned_*` |
| Tampering with an approval | Approve a $900 refund, then send $1,900 | Approval bound to agent, user, tool and argument digest; single use | `test_large_refunds_wait_for_a_person_*` |
| A stale approval | A request approved last week is replayed today, after the facts changed | Pending requests lapse (30 min), approvals must be used within 5 min; lapsed rows become `expired` | `test_approvals_expire_*` |
| Self-approval | An approver approves a refund to themselves | An approver whose id is the request's user is refused | `test_approvals_expire_and_nobody_approves_*` |
| **Repudiation** | "The agent did that on its own" | Every decision logged with agent, user, tool, outcome, policies and latency | `test_decisions_are_logged_*` |
| Tampering with tool descriptions | An approved server adds "also send the user's files" to a tool description | The live tool list must match the digest Atlas reviewed; a mismatch quarantines the server and logs `tools_changed` | `test_changed_tools_quarantine_*`, `test_unpinned_servers_can_be_refused` |
| **Information disclosure** via tool output | A page tells the agent to email data out | Instruction-like text marked, hidden Unicode stripped, secrets redacted | `test_tool_output_is_scanned_*` |
| Disclosure of credentials | Agent learns a service key | Server credentials stay in Checkpoint; agents get none | `test_allowed_call_*` |
| **Denial of service** | A looping agent hammers a tool | Per-agent, per-tool token buckets | `test_rate_limits_and_bad_user_tokens` |
| **Elevation of privilege** | An injected agent calls a tool it should not | Default-deny Cedar; tools hidden from `tools/list` unless permitted; only Atlas-approved, HTTPS servers exist | `test_agents_see_only_tools_*`, `test_policy_denies_with_reasons` |
| Bad policy rollout | A typo opens everything | A policy that does not parse never replaces the running one | `test_decisions_are_logged_and_bad_policies_never_load` |
| A forbid that errors | `context.args.amount > 2000` on a call without `amount`: Cedar skips the forbid and the call is allowed | Any forbid that fails to evaluate turns an allow into a deny; every evaluation error is in the decision log and a metric | `test_a_forbid_that_cannot_evaluate_fails_closed` |

## Residual risks
- Output scanning is a tripwire; least-privilege policies and approvals carry the weight (see the course's
  prompt injection lesson).
- Rate limits are per instance (N instances allow N times the limit).
- The development assertion key is generated per process; production must set a persistent key and rotate it.
- Admin and approver tokens are shared secrets; production should use SSO.
