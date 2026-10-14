---
id: w5-scaling
week: 5
kind: lesson
title: Caching, rate limits, and async execution
short: Caching, limits, async
minutes: 55
summary: The levers that make an AI system faster and cheaper at scale, prompt caching, response caching, model routing, batching, concurrency control, retries, and fallbacks, and the trade-offs of each.
---

## The scaling problem is usually upstream

Your API can scale horizontally almost without limit. Your model provider cannot, at least not for you: you have rate limits on requests per minute and tokens per minute per model, and latency you do not control. Scaling an AI system is mostly about **using fewer tokens, using cheaper tokens, and using your quota well**.

The levers, roughly in order of payoff per unit of effort:

| Lever | Saves | Effort | Risk |
|---|---|---|---|
| Prompt caching | Input cost (90 to 95% off the cached part), TTFT | Low | Low |
| Trimming context (tool results, history) | Input cost, latency | Low to medium | Medium (quality) |
| Shorter outputs | Output cost, latency | Low | Low to medium |
| Model routing (small model for easy traffic) | Cost, latency | Medium | Medium (quality) |
| Exact-match response caching | Everything, for repeats | Low | Low |
| Semantic caching | Everything, for near-repeats | Medium | High (wrong answers, leaks) |
| Batch API for offline work | ~50% on batch jobs | Low | None for offline |
| Lower effort / thinking settings | Cost, latency | Low | Medium (quality) |

## Prompt caching

Providers cache the processed state of a prompt **prefix**. When the next request starts with the same bytes, those tokens are read from cache at a steep discount and with lower latency. For agents, where every loop iteration resends the system prompt, tools, and history, this is the most important cost lever. See the [prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) for exact rules.

How to get high hit rates:

- **Stable prefix first.** System prompt and tool definitions identical across all users and requests. No timestamps, names, or request IDs in them.
- **Deterministic serialisation.** Sort tools; serialise JSON with sorted keys.
- **Append, do not rewrite.** Each turn appends to the message list, so the previous turn's whole context is a cached prefix of the next request.
- **Put cache breakpoints** where your provider requires them (for example on the system prompt and the last message), or use automatic caching where offered.
- **Mind the TTL.** The default cache lifetime is 5 minutes, refreshed each time it is read. A 1-hour option costs 2x base input to write instead of 1.25x. Long pauses between turns lose a 5-minute cache.
- **Mind minimum sizes.** Prefixes shorter than the model's minimum (512 tokens on current Claude models, more on some older ones) are silently not cached.

> [!numbers] An agent turn with 12,000 prefix tokens (system + tools + history) and 3 loop iterations, on Sonnet 5.5. Prices per million tokens: $2 input, $2.50 for a 5-minute cache write (1.25x), $0.10 for a cache read (0.05x). Without caching: 3 × 12,000 × $2 / 1e6 = **$0.072**. With caching, the first call writes the prefix and the next two read it: 12,000 × $2.50 / 1e6 + 2 × 12,000 × $0.10 / 1e6 = $0.030 + $0.0024 = **$0.032** (ignoring the small per-step growth). The write premium is paid back after a single read, and across a long conversation the savings compound as history grows.

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

Providers enforce limits per minute on requests and tokens. Exceeding them returns `429`. Design for it:

- **Client-side throttling.** Keep a shared token bucket (in Redis) per model that tracks tokens per minute across all instances, and make callers wait for capacity rather than firing and failing.
- **Retry with exponential backoff and jitter** on 429, 5xx, overloaded, and timeouts, honouring the `retry-after` header. Jitter prevents synchronised retry storms. See AWS's [Timeouts, retries and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/).
- **Cap retries and total time.** A user-facing request should give up (and fall back) within its latency budget.
- **Prioritise.** Interactive traffic gets first claim on quota; batch work uses what is left, or the batch API.

```python
import random, asyncio
import anthropic

RETRYABLE = (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError, anthropic.APITimeoutError)

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

(The official SDKs already retry some errors by default. Know what your client does so you do not multiply retries: two layers of 3 retries is 16 attempts.)

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

Work that does not need an immediate answer, such as nightly evals, back-filling contextual chunk descriptions, re-classifying old tickets, or generating synthetic data, should use the provider's **batch API**: submit many requests, get results within hours, typically at about half price, and on separate capacity from your interactive traffic.

## Fallbacks and graceful degradation

When the primary model is rate-limited or down:

1. Retry briefly (above).
2. Fall back to another model or another provider region. Abstraction layers such as [LiteLLM](https://docs.litellm.ai/docs/) can route across providers, but every fallback model must be in your eval suite: behaviour, tool calling, and refusals differ.
3. Degrade features: turn off optional steps (reranking, query rewriting) to save time; serve cached FAQ answers for common questions; offer a human handoff.
4. Fail clearly: "Our assistant is busy, here is how to reach support" beats a spinner.

Wrap provider calls in a **circuit breaker** ([Fowler](https://martinfowler.com/bliki/CircuitBreaker.html)): after N consecutive failures, stop calling for a cool-down period and go straight to the fallback, instead of making every user wait for timeouts.

## Design review questions

> [!interview] What is your cache hit rate, and what is the cost per conversation with and without caching?

> [!interview] Show me two questions your semantic cache would wrongly treat as the same. Why is that safe or unsafe?

> [!interview] At what traffic level do you hit the provider's token-per-minute limit, and what happens to the next user?

> [!interview] How many total attempts can a single model call make, counting SDK retries and your own?

## Further reading

- [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), Claude Platform docs.
- [Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/), Amazon Builders' Library.
- [Exponential backoff and jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/), AWS Architecture Blog.
- [Circuit Breaker](https://martinfowler.com/bliki/CircuitBreaker.html), Martin Fowler.
- [LLM numbers every developer should know](https://github.com/ray-project/llm-numbers), Anyscale (dated prices, still useful ratios).
- [Artificial Analysis](https://artificialanalysis.ai/) for independent latency and price comparisons across models.

```quiz
[
  {"q": "Why does appending (not rewriting) the conversation each turn matter for cost?", "options": ["It uses less storage", "The previous request becomes a byte-identical prefix of the next one, so it is served from the prompt cache", "Providers require it", "It shortens outputs"], "answer": 1, "why": "Prefix caching needs identical leading bytes. Rewriting history invalidates the cache from the first changed byte."},
  {"q": "Which item is safest to semantic-cache?", "options": ["Personalised order answers", "Generic policy answers keyed with KB version, with a strict validated threshold", "Answers that depend on conversation history", "Refund decisions"], "answer": 1, "why": "Only context-free, permission-free answers are candidates, and the key must capture what the answer depends on."},
  {"q": "Why add jitter to exponential backoff?", "options": ["To make retries faster", "To spread retries out so many clients do not retry in synchronised waves", "Providers require it", "To reduce token use"], "answer": 1, "why": "Without jitter, clients that failed together retry together, recreating the overload."},
  {"q": "Your SDK retries 3 times by default and your wrapper retries 3 times around it. How many attempts can one call make?", "options": ["3", "6", "9", "16"], "answer": 3, "why": "Each of 4 wrapper attempts (1 + 3 retries) makes up to 4 SDK attempts: 4 × 4 = 16. Know your layers."},
  {"q": "What does a circuit breaker do for a failing provider?", "options": ["Retries faster", "After repeated failures, stops calling it for a cool-down and goes straight to the fallback", "Caches all responses", "Switches off logging"], "answer": 1, "why": "It avoids making every request wait for timeouts while the dependency is down."}
]
```
