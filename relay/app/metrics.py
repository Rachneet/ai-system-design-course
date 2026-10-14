"""Prometheus metrics. Labels are bounded sets (model, tool, route, reason); never user or session IDs."""

from prometheus_client import Counter, Histogram

TURN_BUCKETS = (0.5, 1, 2, 3, 5, 8, 12, 20, 30, 60)

turns = Counter("relay_chat_turns_total", "Chat turns", ["outcome"])  # ok | stopped | error
ttft = Histogram("relay_ttft_seconds", "Time to first streamed text", buckets=TURN_BUCKETS)
turn_seconds = Histogram("relay_turn_seconds", "Full turn duration", buckets=TURN_BUCKETS)
llm_calls = Counter("relay_llm_calls_total", "Model calls", ["model", "finish"])
llm_tokens = Counter(
    "relay_llm_tokens_total", "Model tokens", ["model", "kind"]
)  # input|cache_read|cache_write|output
llm_cost = Counter("relay_llm_cost_usd_total", "Estimated model spend in USD", ["model"])
provider_errors = Counter("relay_provider_errors_total", "Model provider errors", ["model", "type"])
fallbacks = Counter("relay_llm_fallbacks_total", "Requests served by the fallback model", ["reason"])
steps = Histogram("relay_agent_steps", "Model calls per turn", buckets=(1, 2, 3, 4, 5, 6, 8, 10))
stopped = Counter("relay_agent_stopped_total", "Turns that ended early", ["reason"])
tool_calls = Counter("relay_tool_calls_total", "Tool calls", ["tool", "outcome"])
guardrail_fires = Counter("relay_guardrail_fires_total", "Drafts blocked by output guardrails", ["kind"])
routes = Counter("relay_routes_total", "Router decisions", ["route"])
feedback = Counter("relay_feedback_total", "User feedback", ["rating"])
online_verdicts = Counter("relay_online_judge_verdicts_total", "Online judge verdicts", ["judge", "verdict"])
jobs = Counter("relay_jobs_total", "Background jobs", ["kind", "outcome"])
