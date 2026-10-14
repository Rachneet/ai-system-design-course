---
id: w5-monitoring
week: 5
kind: lesson
title: Monitoring errors, token usage, and user feedback
short: Monitoring cost + quality
minutes: 45
summary: The metrics that tell you whether an AI system is healthy, affordable, and actually helping users, and how to collect explicit and implicit feedback and turn it into online evaluation.
---

## Three questions every dashboard answers

1. **Is it working?** Errors, latency, availability, dependency health.
2. **What does it cost?** Tokens, dollars, per user, per tenant, per feature.
3. **Is it any good?** Quality signals from users, judges, and outcomes.

Traditional services stop at the first. AI systems fail quietly on the second and third: a prompt change that makes answers 30% longer doubles the bill without a single error; a retrieval regression makes answers worse with every request returning 200 OK.

## Golden signals, adapted

The classic four (latency, traffic, errors, saturation, from Google's [SRE book](https://sre.google/sre-book/monitoring-distributed-systems/)) still apply, with AI-specific detail:

| Signal | What to track | Why |
|---|---|---|
| Latency | TTFT p50/p95, total turn time p50/p95, per-stage (retrieval, model, tools) | Users feel TTFT; total time affects abandonment |
| Traffic | Conversations, turns, model calls per turn, by route and model | Calls-per-turn growth is often a looping or prompt bug |
| Errors | HTTP 5xx; provider errors by type (429, 5xx, overloaded, timeouts); tool errors by tool; refusals; step-limit hits; guardrail blocks | Many AI failures are not exceptions |
| Saturation | Provider rate-limit headroom (tokens/min used vs limit), worker queue depth and age, DB connections | Rate limits are the usual bottleneck |

## Token and cost monitoring

Record usage on every model call (you already have it in spans): model, input tokens, cached input tokens, output tokens, and the feature, user, and tenant it served. Compute cost from a price table versioned in your repo.

```python
PRICES = {  # USD per million tokens, from the provider's pricing page (checked 2026-10-14)
    "claude-opus-5-5":   {"in": 4.00, "cache_write": 5.00,  "cache_read": 0.20, "out": 20.00},
    "claude-sonnet-5-5": {"in": 2.00, "cache_write": 2.50,  "cache_read": 0.10, "out": 10.00},
    "claude-haiku-5-5":  {"in": 0.10, "cache_write": 0.125, "cache_read": 0.01, "out": 0.50},  # prompts ≤100k tokens
}

def cost_usd(model, usage) -> float:
    p = PRICES[model]
    # The three input counts are disjoint: input_tokens is only the uncached part.
    return (usage.input_tokens * p["in"]
            + (usage.cache_creation_input_tokens or 0) * p["cache_write"]   # 5-minute writes
            + (usage.cache_read_input_tokens or 0) * p["cache_read"]
            + usage.output_tokens * p["out"]) / 1e6
```

> [!warn] Check exactly how your provider reports cached tokens and cache writes. On the Claude API, `input_tokens`, `cache_creation_input_tokens`, and `cache_read_input_tokens` are separate counts that add up to the total input. Cache writes cost more than normal input (1.25x for 5-minute, 2x for 1-hour caches), and Haiku 5.5 charges higher rates when a prompt exceeds 100,000 tokens. Getting this wrong makes your cost dashboards disagree with the invoice, and nobody trusts a dashboard that disagrees with the invoice. Reconcile against the provider's usage report monthly.

Dashboards to build:

- **Cost per conversation** (p50, p95, max) over time, by route and model. The single most useful AI cost chart.
- **Tokens per turn**, split into input, cached input, and output. Rising input means context bloat; rising output means verbosity.
- **Cache hit rate** (cached input / total input). A sudden drop means a prefix change broke caching.
- **Spend by tenant and by feature**, for pricing and abuse detection.
- **Top 20 most expensive conversations** this week, linked to their traces. Read them. They are usually loops, huge tool results, or abuse.

> [!numbers] Relay's p50 conversation costs $0.012 but p99 costs $0.85. The top 1% of conversations is about 0.01 × 0.85 / (0.99 × 0.012 + 0.01 × 0.85) ≈ **42% of total spend** (using p99 as a rough stand-in for the tail). Fixing the tail (step limits, result truncation, compaction) often saves more than optimising the median.

## Quality monitoring

### Explicit feedback

Thumbs up/down, star ratings, "report a problem". Cheap to add, but:

- Response rates are low (often 1 to 5%) and skewed toward unhappy users.
- A thumbs-down without a reason is hard to act on. Offer quick reason chips ("wrong info", "didn't do what I asked", "too long", "unsafe") and an optional comment.
- Always store the trace ID with feedback.

### Implicit feedback

Behaviour tells you more, more often:

| Signal | Suggests |
|---|---|
| User rephrases the same question | The answer missed |
| User asks for a human / escalation rate | The agent could not resolve it |
| Conversation abandoned mid-flow | Frustration or slowness |
| Copy or click on a cited source | The answer was useful |
| Repeat contact on the same order within 48 hours | The issue was not actually resolved |
| Refund reversed or approval rejected by staff | The agent proposed a wrong action |

Define a **resolution rate**: the share of conversations that end without escalation and without repeat contact within N days. It is a better north-star metric for a support agent than thumbs-up rate.

### Online evaluation

Run your Week 3 judges on a sample of live conversations (for example 5%, plus all conversations with negative signals). Chart judge pass rates per category over time. A drop after a deploy is a regression; a slow drift may mean user behaviour or the knowledge base changed.

```mermaid
flowchart LR
  P[Production traces] --> S{Sampler:<br/>5% random +<br/>all negative signals}
  S --> J[Online judges]
  J --> D[Dashboards:<br/>pass rate by category]
  J -->|fail| RQ[Review queue]
  RQ --> L[Human label + category]
  L --> DS[(Eval dataset)]
  L --> JC[Judge calibration data]
```

Human review of the review queue keeps judges honest and turns production failures into eval cases. Budget a few hours a week for it. This loop is where most quality improvement comes from after launch.

## Error tracking

Use an error tracker (for example [Sentry](https://docs.sentry.io/), which has a free tier) for exceptions with stack traces, grouped and deduplicated. Tag errors with model, prompt SHA, route, and trace ID. Many AI "errors" are not exceptions (a refusal, a guardrail block, a step-limit hit, a malformed tool argument the model retried), so emit them as **metrics and structured events** too.

## Metrics plumbing

A simple, standard stack: OTel metrics (or Prometheus client) → [Prometheus](https://prometheus.io/docs/introduction/overview/) or your cloud's metrics service → [Grafana](https://grafana.com/docs/grafana/latest/) dashboards. LLM observability platforms (Langfuse, Phoenix, and commercial ones) give you token, cost, and feedback views out of the box from traces. Many teams use both: infrastructure metrics in Grafana, conversation-level analytics in an LLM tool.

Watch **cardinality**: do not put user IDs or session IDs as metric labels (millions of series). Put them on traces and events; keep metric labels to bounded sets like route, model, tool, and tenant tier.

## A Relay dashboard

| Row | Panels |
|---|---|
| Health | Requests/min, 5xx rate, provider error rate by type, TTFT p95, turn p95 |
| Cost | $/hour, $/conversation p50/p95/p99, cache hit rate, tokens/turn split, spend by tenant |
| Agent behaviour | Steps per turn histogram, step-limit hits, tool calls by tool, tool error rate, guardrail fires by guardrail |
| Quality | Online judge pass rate by category, resolution rate, escalation rate, thumbs-down rate, review queue size |
| Capacity | Rate-limit headroom per model, queue depth and age, DB connections, instance count |

## Design review questions

> [!interview] What did the most expensive conversation yesterday cost, and why?

> [!interview] How would you notice a 10-point drop in answer quality that throws no errors?

> [!interview] What is your resolution rate, and how is it defined?

> [!interview] Does your cost dashboard match last month's invoice within 5%?

## Further reading

- [Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/), Google SRE book.
- [Building A Generative AI Platform](https://huyenchip.com/2024/07/25/genai-platform.html), Chip Huyen. The observability and feedback sections.
- [Langfuse docs](https://langfuse.com/docs) for cost tracking, scores, and datasets.
- [Arize Phoenix](https://github.com/Arize-ai/phoenix) for open-source tracing and online evals.
- [Prometheus overview](https://prometheus.io/docs/introduction/overview/) and [Grafana docs](https://grafana.com/docs/grafana/latest/).

```quiz
[
  {"q": "Average input tokens per turn rose 40% after a release while error rates stayed flat. What is the likely issue?", "options": ["Traffic growth", "Context bloat: larger prompts, tool results, or history, or broken compaction", "The provider raised prices", "Users typing more"], "answer": 1, "why": "Input growth per turn points to what you put in the context. Check prompt size, tool result size, and compaction."},
  {"q": "Why is resolution rate a better north-star than thumbs-up rate for a support agent?", "options": ["It is easier to compute", "It measures whether the problem was actually solved, from behaviour on all conversations rather than a small, skewed sample", "Users prefer it", "It is always higher"], "answer": 1, "why": "Explicit feedback is sparse and biased. Outcome-based metrics reflect real value."},
  {"q": "Why not use user IDs as metric labels?", "options": ["Privacy only", "Unbounded label values create huge numbers of time series and overwhelm the metrics system", "Prometheus forbids strings", "They are not useful"], "answer": 1, "why": "High cardinality explodes metric storage. Keep per-user detail in traces and events."},
  {"q": "Your cache hit rate dropped from 80% to 5% overnight. What should you check first?", "options": ["Provider status page", "Recent changes to anything at the start of the prompt: system prompt, tool definitions, or their ordering", "User traffic", "Database indexes"], "answer": 1, "why": "Cache hits depend on byte-identical prefixes. A small change near the top invalidates everything after it."}
]
```
