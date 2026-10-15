---
id: w6-tradeoffs
week: 6
kind: lesson
title: Failure modes and cost/performance trade-offs
short: Failure modes + cost
minutes: 55
summary: A catalogue of how agentic systems fail in production with detection and mitigation for each, and a worked cost and latency model you can use to compare designs with real numbers.
---

## A failure mode catalogue

Use this table as a reference during design and review. For each failure, ask: could it happen here, how would we detect it, and what limits the damage?

Start with the evidence on where agent systems actually break. The MAST study (Week 1) labelled 1,600+ traces from 7 multi-agent frameworks and found that most failures are design and verification problems, which you fix with specifications and checks rather than a bigger model.

```viz
caption: Most multi-agent failures trace to the specification or to missing checks. Four modes alone cover over half of all failures.
<div class="vz-bars"><span>system design</span><span class="bar sk"><i class="sk b" style="--w:44%"></i></span><b>44%</b><span>agent misalignment</span><span class="bar sk"><i class="sk b" style="--w:32%"></i></span><b>32%</b><span>task verification</span><span class="bar sk"><i class="sk b" style="--w:24%"></i></span><b>24%</b></div>
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk"><h5>Top design modes</h5><p>step repetition 15.7%</p><p>no stop condition 12.4%</p><p>ignores task spec 11.8%</p><span class="ch sk g">fix: specs, step limits</span></div>
  <div class="vz-panel sk"><h5>Top misalignment</h5><p>reasoning-action mismatch 13.2%</p><p>task derailment 7.4%</p><p>no clarifying question 6.8%</p><span class="ch sk g">fix: handoff contracts</span></div>
  <div class="vz-panel sk"><h5>Top verification</h5><p>incorrect verification 9.1%</p><p>no or partial check 8.2%</p><p>premature stop 6.2%</p><span class="ch sk g">fix: end-state checks</span></div>
</div>
<div class="vz-src">Cemri et al., <a href="https://arxiv.org/abs/2503.13657">Why Do Multi-Agent LLM Systems Fail?</a> (v3, October 2025): 14 failure modes in 3 categories across MetaGPT, ChatDev, HyperAgent, AppWorld, AG2, Magentic-One and OpenManus. Category shares are the sums of the paper's per-mode shares.</div>
```

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
| Provider outage or 429 storm | Provider error rate | Throttling, backoff with jitter, circuit breaker, fallback to a second provider or a self-hosted model through a gateway (LiteLLM, OpenRouter) |
| Duplicate side effects on retry | Unique-constraint violations, reconciliation | Idempotency keys, guarded state transitions |
| Lost background jobs | Queue age, outbox lag | Outbox, at-least-once + idempotent handlers, DLQ |
| Cache collapse after deploy | Cache hit rate | Stable prefix, deploy checks |
| Silent quality regression after model alias moved | Online judges, pinned IDs | Pin model versions, eval on upgrade |
| Fallback provider behaves differently | Per-provider eval scores, tool-call error rate by provider | Run the release suite on every model behind the gateway; normalise tool schemas in one adapter |
| Self-hosted server out of KV cache memory | KV cache usage, preemptions, queue depth, p95 TPOT | Cap context length, autoscale on queue depth, KV-aware routing ([inference lesson](#w5-inference)) |
| Connection exhaustion at scale | DB connection metrics | Pooling, PgBouncer, no connections held across LLM calls |

> [!rule] For every write tool, you should be able to name the eval that proves it is not called when it should not be, and the code check that limits damage when it is.

## Cascading failures in agents

Agent failures compound. A retrieval miss leads the model to search again (more tokens), which pushes the context past the compaction threshold (lost details), which leads to asking the user for the order number again (frustration), which leads to escalation (human cost). When reading traces, look for the **first** thing that went wrong; fixing it often removes several downstream symptoms. This is why error analysis records the first failure, not all of them.

```viz
caption: One retrieval miss becomes four visible symptoms. Fix the first link and the rest disappear.
<div class="vz-cols">
  <div class="vz-panel">
    <div class="vz-row"><span class="ch sk b">1. retrieval miss</span><span>the cause</span></div>
    <span class="arr d sk"></span>
    <div class="vz-row"><span class="ch sk w">2. searches again</span><span>more tokens</span></div>
    <span class="arr d sk"></span>
    <div class="vz-row"><span class="ch sk w">3. context compacted</span><span>details lost</span></div>
  </div>
  <div class="vz-panel">
    <div class="vz-row"><span class="ch sk w">4. asks for order again</span><span>user annoyed</span></div>
    <span class="arr d sk"></span>
    <div class="vz-row"><span class="ch sk w">5. escalates to human</span><span>human cost</span></div>
  </div>
</div>
<div class="vz-row"><span class="ch sk g">record this one</span><span>the first failure in the trace, not the loudest</span></div>
```

## A cost model you can reason with

Build a per-conversation model from measured averages:

`cost/conv = Σ over model calls [ (uncached_in × p_in + cached_in × p_cache + out × p_out) / 1e6 ] + retrieval + rerank + infra share`

### Worked example: Relay, three designs

Measured profile: a conversation averages 3 user turns; each turn averages 2.5 model calls in the agent loop. System prompt + tools = 6,000 tokens. History grows about 1,500 tokens per turn. Tool results and retrieval add 2,500 tokens per call. Output averages 250 tokens per call.

The design is about model **tiers**, not one vendor. Prices per million tokens, from the providers' pricing pages in October 2026:

| Tier | Input | Cache write | Cache read | Output |
|---|---|---|---|---|
| Mid-tier | $2 | $2.50 | $0.10 | $10 |
| Small | $0.10 | | | $0.50 |

Both tiers exist at these list prices from more than one vendor: the mid tier is Anthropic's Claude Sonnet 5.5 or OpenAI's gpt-6.1-sol (OpenAI charges cache writes at 1.25x input on GPT-5.6 and later, as Anthropic does); the small tier is Claude Haiku 5.5 (prompts up to 100,000 tokens) or OpenAI's gpt-6-luna. We ignore small-model caching for simplicity.

Google's Gemini caches repeated prefixes implicitly on 2.5 and newer models. Open-weights models (Llama, Qwen, DeepSeek, Mistral) served on vLLM or Ollama have no token price at all: you pay for GPU hours instead (see the [inference lesson](#w5-inference)). Prices change often: re-check them, and keep the arithmetic in a spreadsheet.

Average input per call: 6,000 (prefix) + ~3,000 (average history) + 2,500 (tool results) ≈ 11,500 tokens. Calls per conversation: 3 × 2.5 = 7.5.

**Design A: mid-tier model for everything, no caching.**
Input: 7.5 × 11,500 × $2 / 1e6 = $0.1725. Output: 7.5 × 250 × $10 / 1e6 = $0.01875. **≈ $0.19 per conversation.**

**Design B: mid-tier model with prompt caching.** Assume 75% of input tokens are read from cache and the other 25% are new tokens written to the cache (stable prefix + appended history).
Input: 7.5 × 11,500 × (0.25 × $2.50 + 0.75 × $0.10) / 1e6 = 7.5 × 11,500 × $0.70 / 1e6 ≈ $0.060. Output unchanged at $0.019. **≈ $0.079 per conversation**, 59% cheaper.

**Design C: B plus routing 60% of conversations to the small model with a 4,000-token prompt and 2 calls per turn.**
Small-model conversation: 3 × 2 = 6 calls × (4,000 + 3,000 + 1,500 = 8,500 in × $0.10 + 250 out × $0.50) / 1e6 = 6 × $0.000975 ≈ $0.006. Blended: 0.6 × $0.006 + 0.4 × $0.079 ≈ **$0.035 per conversation**, 82% cheaper than A.

| | A | B | C |
|---|---|---|---|
| Cost per conversation | $0.19 | $0.079 | $0.035 |
| At 50,000 conversations/day, monthly | $285k | $119k | $53k |
| Complexity | Lowest | Low | Router + 2 prompts + evals per route |
| Quality risk | Baseline | None (same model) | Must verify per category |

```viz
caption: Caching cuts the bill by 59% with the same model and the same answers. Routing takes it to 82% off, but only after evals prove the small model on each route.
<div class="vz-bars"><span>A: no cache</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>$0.19</b><span>B: cached</span><span class="bar sk"><i class="sk w" style="--w:42%"></i></span><b>$0.079</b><span>C: cached + routed</span><span class="bar sk"><i class="sk w" style="--w:18%"></i></span><b>$0.035</b></div>
<div class="vz-cols">
  <div class="vz-panel sk g"><h5>A to B: nearly free</h5><p>same model, stable prompt prefix</p></div>
  <div class="vz-panel sk"><h5>B to C: paid in evals</h5><p>a router, two prompts, a suite per route</p></div>
</div>
<div class="vz-src">Cost per conversation from the worked example above, using list prices on the <a href="https://platform.claude.com/docs/en/about-claude/pricing">Anthropic</a> and <a href="https://developers.openai.com/api/docs/pricing">OpenAI</a> pricing pages (October 2026) and Relay's assumed traffic profile.</div>
```

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
| Skipping reranking | Tens of ms (82 ms in Relay on a CPU) | Recall loss |
| Lower reasoning effort settings | Medium to large | Quality on hard cases |

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
- [A practical guide to building agents](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf), OpenAI, on starting with one agent and layering guardrails.
- [Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/abs/2503.13657), the MAST taxonomy behind the first figure.

```quiz
[
  {"q": "The agent says \"I've issued your refund\" but the refunds table is empty. Which failure mode is this?", "options": ["Retrieval miss", "Hallucinated action", "Looping", "Permission leak"], "answer": 1, "why": "Claimed actions must be checked against tool results and end state."},
  {"q": "In the worked example, why is caching called \"nearly free money\"?", "options": ["Providers give it away", "It cuts cost substantially without changing the model or behaviour, so there is little quality risk", "It eliminates output costs", "It improves accuracy"], "answer": 1, "why": "Same model, same outputs, much cheaper input. Routing saves more but must be validated with evals."},
  {"q": "When reading a failed trace with many problems, which do you record during error analysis?", "options": ["All of them equally", "The first thing that went wrong, since later problems often cascade from it", "The last one", "Only security issues"], "answer": 1, "why": "Upstream failures cause downstream symptoms. Fixing the first often fixes the rest."},
  {"q": "Why re-run design comparisons on major model releases?", "options": ["Required by contracts", "Price and capability changes can make earlier complexity, like routing, unnecessary or make new options viable", "To use more tokens", "Models expire"], "answer": 1, "why": "Trade-offs depend on prices and capabilities, which change quickly."}
]
```
