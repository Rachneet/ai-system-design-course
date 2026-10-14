# Threat model (STRIDE)

Scope: the Switchboard data plane (`/v1/messages`), control plane (`/admin`), Postgres, and the provider credential.

| Threat | Example | Mitigation | Test or control |
|---|---|---|---|
| **Spoofing** an app | Stolen or guessed key | 256-bit random secrets; only SHA-256 stored; constant-time compare; expiry; instant revocation on the issuing instance, ≤30 s elsewhere | `test_auth_policy_and_revocation` |
| Spoofing an admin | Calls to `/admin` | Separate admin token (SSO in production); admin API disabled when unset; every write in `admin_audit` | `test_admin_api_requires_the_admin_token` |
| **Tampering** with usage | Inflating or hiding spend | Append-only ledger keyed by request id; totals derived in the same transaction; no API to edit usage | `test_ledger_batches_and_never_double_counts` |
| Tampering with requests | Injecting provider-only headers | Client `x-api-key` stripped; only allow-listed `anthropic-beta` values forwarded | `test_unlisted_beta_headers_are_dropped` |
| **Repudiation** | "We never changed that policy" | `admin_audit` with actor, action, target, details | `test_policy_change_applies_without_restart` |
| **Information disclosure**: provider key | Key leaks to apps | Provider key only in gateway config, never returned or logged | `test_proxy_meters_and_charges_back` |
| Information disclosure: personal data | Card numbers or emails sent to a provider or stored | `pii_mode` detect or redact; audit bodies always stored redacted and only on opt-in, with expiry and purge | `test_pii_redaction_and_audit` |
| Information disclosure: cross-tenant | One team sees another's usage | Usage reads only via admin API; apps cannot query usage | Design |
| **Denial of service**: cost | A runaway client spends the month's budget in an hour | RPM and TPM limits per app; monthly budgets at org, team and app; 413 on oversized bodies | `test_request_rate_limit`, `test_budget_*` |
| Denial of service: provider outage | All requests hang | Connect and read timeouts; circuit breakers; fallback chains before the first byte | `test_fallback_before_first_byte`, `test_breaker_skips_a_failing_model` |
| **Elevation of privilege** | An app uses a model it is not cleared for, including via fallback | `allowed_models` enforced on the request and on fallback candidates | `test_no_fallback_to_a_model_the_app_may_not_use` |

## Residual risks
- Prompt injection inside request content is out of scope for the gateway; it is an application concern
  (and a future Checkpoint gateway concern for tool calls).
- Revocation lags up to `key_cache_ttl_s` on other instances. Lower it, or add a revocation broadcast, if needed.
- The admin token is a shared secret; production should put `/admin` behind SSO and network policy.
