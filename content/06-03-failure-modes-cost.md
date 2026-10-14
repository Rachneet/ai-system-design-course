---
id: w6-tradeoffs
week: 6
kind: lesson
title: Failure modes and cost/performance trade-offs
short: Failure modes + cost
minutes: 50
summary: A catalogue of how agentic systems fail in production with detection and mitigation for each, and a worked cost and latency model you can use to compare designs with real numbers.
---

## A failure mode catalogue

Use this table as a reference during design and review. For each failure, ask: could it happen here, how would we detect it, and what limits the damage?

### Model behaviour

| Failure | Example | Detect | Mitigate |
|---|---|---|---|
| Hallucinated fact | Invents a 90-day return window | Groundedness judge, citation check | Retrieval quality, cite-or-abstain instructions, citation validation |
| Hallucinated action | Says "refund issued" without calling the tool | End-state evals; reply/tool consistency check | Output check: action claims must match tool results |
| Wrong tool or wrong arguments | Refunds order 1024 instead of 1042 | Trajectory evals, tool error rates | Confirm step for writes, clear tool descriptions, typed schemas |
| Looping | Calls `search_kb` 15 times | Steps per turn, step-limit hits | Step limits, "you already searched X" hints, better tools |
| Premature stop | Answers before checking eligibility | Must-call evals | Prompt rules with reasons, workflow-enforced preconditions |
| Over-refusal | Refuses legitimate safety questions | Refusal rate, labelled sets | Prompt tuning, guardrail precision |
| Verbosity drift | Answers grow 40% after model upgrade | Output tokens per turn | Length guidance, evals with length budgets |
| Instruction conflicts | Two prompt sections give different limits | Prompt review, contradiction evals | Single source of truth for rules |

### Data and retrieval

| Failure | Detect | Mitigate |
|---|---|---|
| Stale or wrong KB content | Freshness metrics; user reports | Ownership of documents, review dates, citations visible to users |
| Deleted doc still retrievable | Deletion test in CI | Tombstones filtered in query, reconciliation |
| Permission leak | Cross-tenant/role evals | Filter in SQL, RLS, cache keys with scope |
| Retrieval miss | Recall@k evals, "I don't know" rate | Hybrid + rerank, query rewrite, chunking fixes |
| Embedding/model version mismatch | Assertion on model ID | Versioned indexes, blue/green |

### Security

| Failure | Detect | Mitigate |
|---|---|---|
| Prompt injection obeyed | Red-team suite, anomaly alerts on writes | Least privilege, isolation, approvals, break the trifecta |
| Data exfiltration via output | Red-team cases on links/images | No arbitrary rendering, egress allow-lists |
| Memory poisoning | Memory audits, red-team | Facts not instructions, trusted sources only |
| Denial of wallet | Per-user spend, cost alerts | Rate limits, budgets, input caps |
| Malicious or compromised MCP server | Tool description diffs, review | Pin versions, minimal credentials, sandbox |

### Infrastructure and operations

| Failure | Detect | Mitigate |
|---|---|---|
| Provider outage or 429 storm | Provider error rate | Throttling, backoff with jitter, circuit breaker, fallback |
| Duplicate side effects on retry | Unique-constraint violations, reconciliation | Idempotency keys, guarded state transitions |
| Lost background jobs | Queue age, outbox lag | Outbox, at-least-once + idempotent handlers, DLQ |
| Cache collapse after deploy | Cache hit rate | Stable prefix, deploy checks |
| Silent quality regression after model alias moved | Online judges, pinned IDs | Pin model versions, eval on upgrade |
| Connection exhaustion at scale | DB connection metrics | Pooling, PgBouncer, no connections held across LLM calls |

> [!rule] For every write tool, you should be able to name the eval that proves it is not called when it should not be, and the code check that limits damage when it is.

## Cascading failures in agents

Agent failures compound. A retrieval miss leads the model to search again (more tokens), which pushes the context past the compaction threshold (lost details), which leads to asking the user for the order number again (frustration), which leads to escalation (human cost). When reading traces, look for the **first** thing that went wrong; fixing it often removes several downstream symptoms. This is why error analysis records the first failure, not all of them.

## A cost model you can reason with

Build a per-conversation model from measured averages:

`cost/conv = Σ over model calls [ (uncached_in × p_in + cached_in × p_cache + out × p_out) / 1e6 ] + retrieval + rerank + infra share`

### Worked example: Relay, three designs

Measured profile: a conversation averages 3 user turns; each turn averages 2.5 model calls in the agent loop. System prompt + tools = 6,000 tokens. History grows about 1,500 tokens per turn. Tool results and retrieval add 2,500 tokens per call. Output averages 250 tokens per call. Prices per million tokens: Sonnet 5.5 $2 input, $2.50 cache write, $0.10 cache read, $10 output; Haiku 5.5 $0.10 input, $0.50 output (we ignore Haiku caching for simplicity).

Average input per call: 6,000 (prefix) + ~3,000 (average history) + 2,500 (tool results) ≈ 11,500 tokens. Calls per conversation: 3 × 2.5 = 7.5.

**Design A: Sonnet for everything, no caching.**
Input: 7.5 × 11,500 × $2 / 1e6 = $0.1725. Output: 7.5 × 250 × $10 / 1e6 = $0.01875. **≈ $0.19 per conversation.**

**Design B: Sonnet with prompt caching.** Assume 75% of input tokens are read from cache and the other 25% are new tokens written to the cache (stable prefix + appended history).
Input: 7.5 × 11,500 × (0.25 × $2.50 + 0.75 × $0.10) / 1e6 = 7.5 × 11,500 × $0.70 / 1e6 ≈ $0.060. Output unchanged at $0.019. **≈ $0.079 per conversation**, 59% cheaper.

**Design C: B plus routing 60% of conversations to Haiku with a 4,000-token prompt and 2 calls per turn.**
Haiku conversation: 3 × 2 = 6 calls × (4,000 + 3,000 + 1,500 = 8,500 in × $0.10 + 250 out × $0.50) / 1e6 = 6 × $0.000975 ≈ $0.006. Blended: 0.6 × $0.006 + 0.4 × $0.079 ≈ **$0.035 per conversation**, 82% cheaper than A.

| | A | B | C |
|---|---|---|---|
| Cost per conversation | $0.19 | $0.079 | $0.035 |
| At 50,000 conversations/day, monthly | $285k | $119k | $53k |
| Complexity | Lowest | Low | Router + 2 prompts + evals per route |
| Quality risk | Baseline | None (same model) | Must verify per category |

> [!numbers] The ordering is typical: caching is nearly free money, routing is a large second step that must be paid for with evals, and everything else (shorter prompts, trimming) is incremental. Your numbers will differ, so measure your own profile and put this table in your design doc.

## Latency trade-offs

Turn latency is roughly: `router + retrieval + Σ over loop steps (TTFT + output_tokens / tokens_per_sec + tool time)`.

Levers and their costs:

| Lever | Latency gain | Cost |
|---|---|---|
| Streaming | Large perceived gain | None |
| Fewer loop steps (better tools, combined tools) | Large | Tool redesign |
| Parallel tool calls | Medium | None if tools independent |
| Smaller/faster model on simple routes | Large | Quality risk; evals |
| Shorter outputs | Large | Product decision |
| Prompt caching | Lower TTFT on long prefixes | None |
| Skipping reranking | 100–300 ms | Recall loss |
| Lower reasoning effort settings | Medium–large | Quality on hard cases |

## Choosing between designs

Make the decision explicit: state the constraint that binds (usually quality floor, then latency, then cost), eliminate designs that violate it, and pick the cheapest remaining one that the team can operate. Revisit when traffic, prices, or models change. Model prices fall and capabilities rise quickly, so a routing scheme that made sense a year ago may now be complexity without benefit. Re-run the comparison on each major model release.

## Design review questions

> [!interview] Name the three most likely failure modes for your system and show the detection for each.

> [!interview] Walk me through your cost per conversation. What is the biggest line item, and what is your next lever?

> [!interview] If model prices halve tomorrow, which of your design choices would you undo?

## Further reading

- [What We Learned from a Year of Building with LLMs](https://applied-llms.org/), tactical, operational, and strategic lessons.
- [Patterns for Building LLM-based Systems](https://eugeneyan.com/writing/llm-patterns/), Eugene Yan.
- [Artificial Analysis](https://artificialanalysis.ai/), for comparing models on price, speed, and quality.
- [12-factor agents](https://github.com/humanlayer/12-factor-agents).
- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents), on when complexity pays.

```quiz
[
  {"q": "The agent says \"I've issued your refund\" but the refunds table is empty. Which failure mode is this?", "options": ["Retrieval miss", "Hallucinated action", "Looping", "Permission leak"], "answer": 1, "why": "Claimed actions must be checked against tool results and end state."},
  {"q": "In the worked example, why is caching called \"nearly free money\"?", "options": ["Providers give it away", "It cuts cost substantially without changing the model or behaviour, so there is little quality risk", "It eliminates output costs", "It improves accuracy"], "answer": 1, "why": "Same model, same outputs, much cheaper input. Routing saves more but must be validated with evals."},
  {"q": "When reading a failed trace with many problems, which do you record during error analysis?", "options": ["All of them equally", "The first thing that went wrong, since later problems often cascade from it", "The last one", "Only security issues"], "answer": 1, "why": "Upstream failures cause downstream symptoms. Fixing the first often fixes the rest."},
  {"q": "Why re-run design comparisons on major model releases?", "options": ["Required by contracts", "Price and capability changes can make earlier complexity, like routing, unnecessary or make new options viable", "To use more tokens", "Models expire"], "answer": 1, "why": "Trade-offs depend on prices and capabilities, which change quickly."}
]
```
