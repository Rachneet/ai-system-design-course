# Runbook: model provider errors or outage

**Alert:** ProviderErrorsHigh. Calls to the primary model are failing; ResilientLLM is retrying or falling back.

1. Check the provider's status page and `relay_provider_errors_total` by `type` (RateLimitError vs 5xx vs connection).
2. **Rate limits (429):** check our own traffic first (a bulk job? one tenant?). Lower worker concurrency; consider
   moving batch work to the batch API.
3. **Provider down:** the circuit breaker should already send traffic to the fallback. Make it explicit and stable:
   `PUT /flags {"key": "agent.force_fallback", "value": true}`.
4. If the fallback also fails, pause the assistant (`agent.enabled=false`) and show the support contact.
5. When the provider recovers, unset `agent.force_fallback` and watch error rate and cost for 30 minutes. Retries can
   spike cost on recovery.
