"""Prometheus metrics. Labels are bounded: model, outcome, reason, team. Never key ids or request ids."""

from prometheus_client import Counter, Histogram

LATENCY = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120)

requests = Counter("switchboard_requests_total", "Proxied requests", ["model", "status_class"])
rejections = Counter("switchboard_rejections_total", "Requests refused before reaching a provider", ["reason"])
overhead = Histogram("switchboard_overhead_seconds", "Gateway time before the upstream call starts", buckets=LATENCY)
ttfb = Histogram("switchboard_upstream_ttfb_seconds", "Upstream time to first byte", ["model"], buckets=LATENCY)
duration = Histogram("switchboard_request_seconds", "Total request duration", ["model"], buckets=LATENCY)
tokens = Counter("switchboard_tokens_total", "Tokens by kind", ["model", "kind"])
cost = Counter("switchboard_cost_usd_total", "Spend in USD", ["model", "team"])
fallbacks = Counter("switchboard_fallbacks_total", "Requests served by a fallback model", ["requested", "served"])
upstream_errors = Counter("switchboard_upstream_errors_total", "Provider errors", ["model", "kind"])
pii = Counter("switchboard_pii_findings_total", "Personal data found in requests", ["mode"])
