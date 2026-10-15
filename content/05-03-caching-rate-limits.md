---
id: w5-scaling
week: 5
kind: lesson
title: Caching, rate limits, and async execution
short: Caching, limits, async
minutes: 65
summary: The levers that make an AI system faster and cheaper at scale, prompt caching, response caching, model routing, batching, concurrency control, retries, and fallbacks, and the trade-offs of each.
---

## The scaling problem is usually upstream

Your API can scale horizontally almost without limit. Your model provider cannot, at least not for you: every hosted API (Anthropic, OpenAI, Gemini, and the routers in front of them) limits requests per minute and tokens per minute per model, and you do not control its latency. If you self-host an open model on vLLM or Ollama, the limit becomes your own GPUs. Scaling an AI system is mostly about **using fewer tokens, using cheaper tokens, and using your quota well**.

The levers, roughly in order of payoff per unit of effort:

| Lever | Saves | Effort | Risk |
|---|---|---|---|
| Prompt caching | Input cost (about 90% off cached input on most hosted APIs), TTFT | Low | Low |
| Trimming context (tool results, history) | Input cost, latency | Low to medium | Medium (quality) |
| Shorter outputs | Output cost, latency | Low | Low to medium |
| Model routing (small model for easy traffic) | Cost, latency | Medium | Medium (quality) |
| Exact-match response caching | Everything, for repeats | Low | Low |
| Semantic caching | Everything, for near-repeats | Medium | High (wrong answers, leaks) |
| Batch API for offline work | 50% on batch jobs (Anthropic, OpenAI, Gemini) | Low | None for offline |
| Lower effort / thinking settings | Cost, latency | Low | Medium (quality) |

Reasoning tokens are billed as output, the expensive and sequential kind, so thinking settings and model routing are among the biggest levers here. [Reasoning and test-time compute](#uth-reasoning) works through when thinking longer pays.

## Prompt caching

Providers cache the processed state of a prompt **prefix** (the KV cache from the [inference lesson](#w5-inference)). When the next request starts with the same tokens, those tokens are read from cache at a steep discount and with lower latency. For agents, where every loop iteration resends the system prompt, tools, and history, this is the most important cost lever.

The idea is the same everywhere; the mechanics are not. Some providers cache automatically, one asks you to mark what to cache, some charge extra to write the cache, and the lifetimes differ:

| | Anthropic | OpenAI | Google Gemini | Self-hosted: vLLM, SGLang |
|---|---|---|---|---|
| How | Explicit `cache_control` breakpoints (up to 4), or one top-level `cache_control` that moves the breakpoint forward automatically | Automatic for supported models; optional `prompt_cache_key` to group related requests | **Implicit**: automatic on Gemini 2.5 and newer, no saving guaranteed. **Explicit**: create a cache object with `caches.create` and reference it | Automatic prefix caching, on by default in vLLM; SGLang's RadixAttention reuses prefixes automatically |
| Minimum prompt | 512 tokens on current models; 1,024 to 4,096 on older ones | 1,024 tokens on GPT-5.6 and later; varies on earlier models | Implicit: 2,048 tokens on 2.5 Flash and Pro, 4,096 on newer models | none: whole KV blocks are reused |
| Cache read | 0.1x input (0.05x on Opus and Sonnet 5.5) | 0.1x input on GPT-5 and GPT-5.6 | 0.1x input on 2.5 Flash | free: skips prefill on your GPU |
| Cache write | 1.25x input (5-minute) or 2x (1-hour) | no premium on earlier models; 1.25x on GPT-5.6 and later | no premium for implicit; explicit caches pay storage per token-hour | free, but uses GPU memory |
| Lifetime | 5 minutes, refreshed on every hit; 1-hour option | 30 minutes after last use on GPT-5.6 and later; earlier models keep it in memory for minutes, or up to 24 hours with extended retention | Explicit: 1 hour by default, any TTL you pay for | until evicted (least recently used first) |

Sources, checked 2026-10-14: Anthropic [prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) and [pricing](https://platform.claude.com/docs/en/about-claude/pricing); OpenAI [prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) and [pricing](https://developers.openai.com/api/docs/pricing); Gemini [context caching](https://ai.google.dev/gemini-api/docs/generate-content/caching) and [pricing](https://ai.google.dev/gemini-api/docs/pricing); vLLM [prefix caching design](https://docs.vllm.ai/en/latest/design/prefix_caching.html) and [`enable_prefix_caching` default](https://github.com/vllm-project/vllm/blob/main/vllm/config/cache.py); SGLang [RadixAttention](https://lmsys.org/blog/2024-01-17-sglang/); llama.cpp's server, which Ollama-style local setups build on, also reuses the previous prompt's cache by default ([`cache_prompt`](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)). Routers such as OpenRouter and LiteLLM pass requests to these providers, so the upstream provider's rules apply. These details change often: check the docs for the models you use.

How to get high hit rates, on any provider:

- **Stable prefix first.** System prompt and tool definitions identical across all users and requests. No timestamps, names, or request IDs in them.
- **Deterministic serialisation.** Sort tools; serialise JSON with sorted keys. Tool definitions and output schemas are part of the cached prefix on every provider.
- **Append, do not rewrite.** Each turn appends to the message list, so the previous turn's whole context is a cached prefix of the next request.
- **Mark the cache where your provider asks.** On Anthropic, put `cache_control` on the system prompt and the last message, or use the top-level automatic form. On OpenAI and Gemini implicit caching there is nothing to mark, so prefix order is everything.
- **Mind the lifetime.** A 5-minute cache is lost when a user pauses for coffee. Longer options exist (Anthropic's 1-hour cache, OpenAI's extended retention, Gemini explicit caches) at a write or storage cost.
- **Mind minimum sizes.** Prefixes shorter than the provider's minimum are silently not cached, with no error.

> [!numbers] An agent turn with 12,000 prefix tokens (system + tools + history) and 3 loop iterations, ignoring the small per-step growth. Prices per million tokens, checked 2026-10-14. **Anthropic, Sonnet 5.5** ($2 input, $2.50 5-minute write, $0.10 read): without caching 3 × 12,000 × $2 / 1e6 = **$0.072**; with caching the first call writes and the next two read: 12,000 × $2.50 / 1e6 + 2 × 12,000 × $0.10 / 1e6 = **$0.032**. **OpenAI, GPT-5** ($1.25 input, no write premium, $0.125 cached): without caching **$0.045**; with caching 12,000 × $1.25 / 1e6 + 2 × 12,000 × $0.125 / 1e6 = **$0.018**. **Gemini 2.5 Flash** ($0.30 input, $0.03 cached): without caching **$0.0108**; if both later calls hit the implicit cache, **$0.0043**. The per-token prices differ by more than 6x, but the lesson is the same: caching cuts this loop's input bill by more than half, and the savings grow with every turn of history.

```viz
caption: Three providers, three mechanisms, the same result: with caching, this 3-step agent loop pays well under half the input bill.
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk"><h5>Anthropic Sonnet 5.5</h5>
    <div class="vz-bars"><span>no cache</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>$0.072</b><span>cached</span><span class="bar sk"><i class="sk g" style="--w:45%"></i></span><b>$0.032</b></div>
    <p>explicit, write costs 1.25x</p>
  </div>
  <div class="vz-panel sk"><h5>OpenAI GPT-5</h5>
    <div class="vz-bars"><span>no cache</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>$0.045</b><span>cached</span><span class="bar sk"><i class="sk g" style="--w:40%"></i></span><b>$0.018</b></div>
    <p>automatic, no write premium</p>
  </div>
  <div class="vz-panel sk"><h5>Gemini 2.5 Flash</h5>
    <div class="vz-bars"><span>no cache</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>$0.011</b><span>cached</span><span class="bar sk"><i class="sk g" style="--w:40%"></i></span><b>$0.004</b></div>
    <p>implicit, hits not guaranteed</p>
  </div>
</div>
<div class="vz-row"><b>request 2:</b><span class="ch wide sk g">12,000-token prefix: read from cache</span><span class="ch sk c">new turn</span></div>
<div class="vz-src">12,000-token prefix, 3 calls. Prices from the <a href="https://platform.claude.com/docs/en/about-claude/pricing">Anthropic</a>, <a href="https://developers.openai.com/api/docs/pricing">OpenAI</a> and <a href="https://ai.google.dev/gemini-api/docs/pricing">Gemini</a> pricing pages, checked 2026-10-14. Bars are relative to each provider's own uncached cost.</div>
```

Caching also raises your effective rate limit on some providers: on most Claude models, cache reads do not count toward the input-tokens-per-minute limit ([rate limits](https://platform.claude.com/docs/en/api/rate-limits#cache-aware-itpm)).

## Response caching

### Exact-match caching

Hash the full normalised request (model, prompt version, system, messages, tools, parameters) and cache the response. Hit rates are low for chat, but high for:

- Deterministic pipeline steps (classifying the same product description, summarising the same document).
- Embeddings of the same text (always cache these).
- Repeated eval runs and judge calls.

### Semantic caching

Embed the user's question; if a previous question is within a similarity threshold, return its answer. Tools like [GPTCache](https://github.com/zilliztech/GPTCache) and Redis vector search implement this. It is tempting and dangerous:

- "Can I return a used tent?" and "Can I return an unused tent?" are very similar embeddings with opposite answers.
- Answers depend on context the cache key may not include: the user's orders, permissions, conversation history, today's date, the current policy version.
- A cross-user hit can **leak** one user's personalised or permission-restricted answer to another.

> [!rule] Only semantic-cache answers that are generic (no user data, no permissions, no history), include the knowledge-base version and permission scope in the key, use a strict threshold validated on labelled pairs, and expire entries when the underlying documents change.

For most agents, semantic caching of final answers is not worth the risk. Caching **retrieval results** or **query rewrites** for popular queries is safer and still saves latency.

## Model routing and cascades

Send each request to the cheapest model that can handle it:

- **Classifier routing**: a small model (or a fine-tuned classifier) labels the intent and difficulty, and a rule picks the model and toolset.
- **Cascades**: try a small model first; if a confidence check or validator fails, escalate to a larger model. Works well when failures are detectable (schema validation, a judge, tool errors).

Measure routing with evals: the routed system must hold quality on every category, not only on average. Also measure the simpler alternative first: a capable model at a lower effort setting may match a cascade with less complexity and one cache namespace (caches are per model, so routing between models reduces cache reuse).

## Rate limits: yours and theirs

### Respecting provider limits

Every hosted provider enforces limits per minute on requests and tokens, and returns HTTP `429` when you exceed them, usually with a hint for when to retry:

| Provider | What is limited | When you exceed it |
|---|---|---|
| [Anthropic](https://platform.claude.com/docs/en/api/rate-limits) | Requests, input tokens and output tokens per minute (RPM, ITPM, OTPM), per model, refilled continuously as a token bucket | `429 rate_limit_error` with `retry-after`; `anthropic-ratelimit-*` headers show what is left. Overload is a separate `529` |
| [OpenAI](https://developers.openai.com/api/docs/guides/rate-limits) | Requests and tokens per minute and per day; `max_tokens` counts toward the token estimate | `429`, `Retry-After` when present; `x-ratelimit-*` headers. Overload is a `503` |
| [Gemini](https://ai.google.dev/gemini-api/docs/rate-limits) | Requests per minute, input tokens per minute, requests per day, per project (not per key) | `429 RESOURCE_EXHAUSTED`; retry with exponential backoff ([troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting)) |
| [OpenRouter](https://openrouter.ai/docs/api/reference/limits) | Its own caps on free models, plus each upstream provider's limits | Passes upstream `429`s through; can fall back to other providers or models for you |
| Self-hosted (vLLM, Ollama) | No quota: your GPUs | Requests queue and latency climbs, so add your own limiter |

```viz
caption: A token bucket refills at a steady rate. Requests take tokens; when the bucket is empty the provider says 429, and a client-side bucket makes your callers wait instead.
<div class="vz-cols">
  <div class="vz-panel sk"><h5>Tokens-per-minute bucket</h5>
    <div class="vz-row"><span class="ch sk">refill: limit per minute</span></div><span class="arr d sk"></span>
    <div class="cells" style="--n:8"><i class="sk fill g"></i><i class="sk fill g"></i><i class="sk fill g"></i><i class="sk fill g"></i><i class="sk fill g"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i></div>
    <div class="vz-row"><span class="ch sk c">request: 3 cells</span><span class="arr sk"></span><span class="ch sk g">allowed</span></div>
    <div class="vz-row"><span class="ch sk c">request: 4 cells</span><span class="arr sk"></span><span class="ch sk b">429, retry-after</span></div>
  </div>
  <div class="vz-panel sk"><h5>Your side</h5>
    <div class="vz-row"><span class="ch sk c">shared bucket in Redis</span><span class="arr sk"></span><span class="ch sk g">wait for capacity</span></div>
    <div class="vz-row"><span class="ch sk b">429</span><span class="arr sk"></span><span class="ch sk">backoff + jitter</span><span class="arr sk"></span><span class="ch sk">fallback</span></div>
    <p>interactive traffic first, batch takes the rest</p>
  </div>
</div>
<div class="vz-src">Anthropic documents its limits as a <a href="https://platform.claude.com/docs/en/api/rate-limits">token bucket</a>; OpenAI and Gemini also limit requests and tokens per minute (<a href="https://developers.openai.com/api/docs/guides/rate-limits">OpenAI</a>, <a href="https://ai.google.dev/gemini-api/docs/rate-limits">Gemini</a>).</div>
```

Design for it:

- **Client-side throttling.** Keep a shared token bucket (in Redis) per provider and model that tracks tokens per minute across all instances, and make callers wait for capacity rather than firing and failing. Gateways such as the [LiteLLM router](https://docs.litellm.ai/docs/routing) can do this for you: they track RPM and TPM per deployment, back off on rate-limit errors, and cool a deployment down after a 429.
- **Retry with exponential backoff and jitter** on 429, 5xx, overloaded (Anthropic's 529, OpenAI's 503), and timeouts, honouring the `retry-after` header. Jitter prevents synchronised retry storms. See AWS's [Timeouts, retries and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/).
- **Cap retries and total time.** A user-facing request should give up (and fall back) within its latency budget.
- **Prioritise.** Interactive traffic gets first claim on quota; batch work uses what is left, or the batch API.

```python
import random, asyncio
import anthropic, openai   # openai also covers Gemini, OpenRouter, vLLM and Ollama through their OpenAI-compatible endpoints

RETRYABLE = tuple(
    getattr(sdk, name) for sdk in (anthropic, openai)
    for name in ("RateLimitError", "InternalServerError", "APIConnectionError", "APITimeoutError")
)

async def call_with_retry(fn, *, attempts=4, base=0.5, cap=8.0, deadline_s=20.0):
    start = asyncio.get_running_loop().time()
    for i in range(attempts):
        try:
            return await fn()
        except RETRYABLE as e:
            retry_after = getattr(getattr(e, "response", None), "headers", {}).get("retry-after")
            delay = float(retry_after) if retry_after else random.uniform(0, min(cap, base * 2 ** i))  # full jitter
            if i == attempts - 1 or asyncio.get_running_loop().time() - start + delay > deadline_s:
                raise
            await asyncio.sleep(delay)
```

(The official SDKs already retry some errors by default: the Anthropic and OpenAI Python SDKs retry twice, with backoff ([Anthropic](https://platform.claude.com/docs/en/api/errors), [OpenAI](https://github.com/openai/openai-python#retries)). Know what your client does so you do not multiply retries: two layers of 3 retries is 16 attempts. Set `max_retries=0` on the SDK if your wrapper owns retries.)

### Your own limits

Per-user and per-tenant limits (Week 4) protect your quota from one customer. Tie them to plans: free users get a small model and low limits; paying tenants get more.

## Async execution and concurrency

- **Async I/O everywhere** on the request path: model client, database driver, HTTP clients. One blocking call in an async server stalls every request on that worker.
- **Parallelise independent work**: retrieval and input guardrails concurrently; parallel tool calls; multi-query retrieval.
- **Bound concurrency** with semaphores so a burst does not open 5,000 simultaneous model calls.
- **Stream** to cut perceived latency: users see the first tokens in under a second even if the full answer takes six.
- **Move non-urgent work off the path**: memory, analytics, online judging, all in workers.
- **Speculate carefully**: start retrieval while the router is still classifying; discard if not needed. Costs a little, saves hundreds of milliseconds.

## Batch processing

Work that does not need an immediate answer, such as nightly evals, back-filling contextual chunk descriptions, re-classifying old tickets, or generating synthetic data, should use the provider's **batch API**: submit many requests, get results within hours, at half price on Anthropic, OpenAI and Gemini ([Anthropic](https://platform.claude.com/docs/en/about-claude/pricing#batch-processing), [OpenAI](https://developers.openai.com/api/docs/pricing), [Gemini](https://ai.google.dev/gemini-api/docs/pricing)), and on separate capacity from your interactive traffic. Batch and caching discounts can stack.

## Fallbacks and graceful degradation

When the primary model is rate-limited or down:

1. Retry briefly (above).
2. Fall back to another model, region or provider. Gateways such as [LiteLLM](https://docs.litellm.ai/docs/routing) and [OpenRouter](https://openrouter.ai/docs/api/reference/limits) can route across providers, and Relay takes a `RELAY_FALLBACK_MODEL` spec on a different provider. Every fallback model must be in your eval suite: behaviour, tool calling, and refusals differ, and its prompt cache starts cold.
3. Degrade features: turn off optional steps (reranking, query rewriting) to save time; serve cached FAQ answers for common questions; offer a human handoff.
4. Fail clearly: "Our assistant is busy, here is how to reach support" beats a spinner.

Wrap provider calls in a **circuit breaker** ([Fowler](https://martinfowler.com/bliki/CircuitBreaker.html)): after N consecutive failures, stop calling for a cool-down period and go straight to the fallback, instead of making every user wait for timeouts.

## Design review questions

> [!interview] What is your cache hit rate, and what is the cost per conversation with and without caching?

> [!interview] Show me two questions your semantic cache would wrongly treat as the same. Why is that safe or unsafe?

> [!interview] At what traffic level do you hit the provider's token-per-minute limit, and what happens to the next user?

> [!interview] How many total attempts can a single model call make, counting SDK retries and your own?

## Further reading

- Prompt caching docs: [Anthropic](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [OpenAI](https://developers.openai.com/api/docs/guides/prompt-caching), [Gemini](https://ai.google.dev/gemini-api/docs/generate-content/caching), [vLLM automatic prefix caching](https://docs.vllm.ai/en/latest/features/automatic_prefix_caching.html).
- Rate limit docs: [Anthropic](https://platform.claude.com/docs/en/api/rate-limits), [OpenAI](https://developers.openai.com/api/docs/guides/rate-limits), [Gemini](https://ai.google.dev/gemini-api/docs/rate-limits).
- [Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/), Amazon Builders' Library.
- [Exponential backoff and jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/), AWS Architecture Blog.
- [Circuit Breaker](https://martinfowler.com/bliki/CircuitBreaker.html), Martin Fowler.
- [LLM numbers every developer should know](https://github.com/ray-project/llm-numbers), Anyscale (dated prices, still useful ratios).
- [Artificial Analysis](https://artificialanalysis.ai/) for independent latency and price comparisons across models.

```quiz
[
  {"q": "Why does appending (not rewriting) the conversation each turn matter for cost?", "options": ["It uses less storage", "The previous request becomes a byte-identical prefix of the next one, so it is served from the prompt cache", "Providers require it", "It shortens outputs"], "answer": 1, "why": "Prefix caching needs identical leading bytes. Rewriting history invalidates the cache from the first changed byte."},
  {"q": "You move Relay's agent from Anthropic to OpenAI. What changes about prompt caching?", "options": ["Nothing at all", "OpenAI caches long prefixes automatically, so the cache_control markers do nothing there, but a stable prefix still decides your hit rate", "Caching stops working", "You must create cache objects by hand"], "answer": 1, "why": "Mechanisms differ (explicit breakpoints against automatic caching), but every provider caches by prefix, so prompt order matters everywhere."},
  {"q": "Which item is safest to semantic-cache?", "options": ["Personalised order answers", "Generic policy answers keyed with KB version, with a strict validated threshold", "Answers that depend on conversation history", "Refund decisions"], "answer": 1, "why": "Only context-free, permission-free answers are candidates, and the key must capture what the answer depends on."},
  {"q": "Why add jitter to exponential backoff?", "options": ["To make retries faster", "To spread retries out so many clients do not retry in synchronised waves", "Providers require it", "To reduce token use"], "answer": 1, "why": "Without jitter, clients that failed together retry together, recreating the overload."},
  {"q": "Your SDK retries 3 times by default and your wrapper retries 3 times around it. How many attempts can one call make?", "options": ["3", "6", "9", "16"], "answer": 3, "why": "Each of 4 wrapper attempts (1 + 3 retries) makes up to 4 SDK attempts: 4 × 4 = 16. Know your layers."},
  {"q": "What does a circuit breaker do for a failing provider?", "options": ["Retries faster", "After repeated failures, stops calling it for a cool-down and goes straight to the fallback", "Caches all responses", "Switches off logging"], "answer": 1, "why": "It avoids making every request wait for timeouts while the dependency is down."}
]
```
