---
id: uth-attention
week: 98
kind: lesson
title: "Under the hood: attention and the KV cache"
short: Attention and KV cache
minutes: 40
summary: Write a tiny decoder in numpy, generate with and without a KV cache, and see why output length drives latency, why prompt caching works, and why long conversations cost memory.
---

## What this explains

Three facts in this course rest on one mechanism:

- **Output length, not input length, usually dominates latency** ([primer](#primer)).
- **Prompt caching** cuts cost and time to first token, but only for an *identical* prefix ([caching](#w5-scaling)).
- **Long conversations are expensive to serve**, even when the provider charges per token ([LLM inference](#w5-inference)).

The mechanism is attention, and the thing that makes it affordable is the key-value (KV) cache. This page builds both in about 100 lines of numpy, so you can see the cache work instead of taking it on trust. The inference lesson then covers how serving engines manage the cache at scale (paging, prefix sharing, GQA and MLA).

## The idea: every token looks back at every earlier token

A decoder model produces one token per forward pass. At every layer, each token is turned into three vectors: a **query** (what am I looking for?), a **key** (what do I offer?) and a **value** (what do I pass on?). A token's new representation is a weighted mix of the values of every token up to and including itself, weighted by how well its query matches each key. A mask stops a token from looking ahead.

```viz
caption: To make the next token, the newest token's query is compared with the keys of every earlier token. The earlier keys and values never change, so they can be kept instead of recomputed.
<div class="vz-cols">
  <div class="vz-panel sk b"><h5>Without a cache</h5>
    <div class="vz-row"><span class="ch sk b">K,V for "My"</span><span class="ch sk b">"order"</span><span class="ch sk b">"is"</span><span class="ch sk b">"late"</span></div>
    <p>every step recomputes K and V for the whole sequence: work grows with the square of the length</p></div>
  <div class="vz-panel sk g"><h5>With a KV cache</h5>
    <div class="vz-row"><span class="ch sk m">cached</span><span class="ch sk m">cached</span><span class="ch sk m">cached</span><span class="ch sk g">new: "late"</span></div>
    <p>each step computes K and V for one new token and reads the rest from memory</p></div>
</div>
```

Generation therefore has two phases. **Prefill** processes the whole prompt at once, in parallel, and fills the cache; it sets the time to the first token. **Decode** then produces one token per step, each step reading the entire cache; it sets the time per output token. Decode cannot be parallelised across the tokens of one answer, because each token depends on the one before. That is why a 400-token answer takes far longer than reading a 20,000-token prompt.

## Run it

```bash
cd under-the-hood && uv sync
uv run python -m uth.kv_cache
```

The script builds a two-layer, four-head decoder with random weights (it makes nonsense tokens, which is fine: we are measuring the machinery), and generates 200 tokens after a 40-token prompt, twice:

```text
no cache     :   172.1 ms,  36,469,600 attention scores, first tokens [29, 3, 39, 39, 39, 39]
with KV cache:    20.5 ms,     237,600 attention scores, first tokens [29, 3, 39, 39, 39, 39]
Identical tokens; the cache turns quadratic recomputation into one new row per step.
```

The same tokens, from about 150 times fewer query-key comparisons. The test suite checks that the two paths produce identical tokens, not merely similar ones. Your timings will differ; the ratio is the point, and it grows with the length of the conversation.

Next, the script computes the cache for a 32-token "system prompt" once, then answers two different user turns that start with it:

```text
user turn [40, 41, 42]: reused 32 cached tokens, same output: True
user turn [50, 51]: reused 32 cached tokens, same output: True
```

This is provider prompt caching in miniature. The cache holds keys and values for an exact sequence of tokens at exact positions. Any request that begins with the same tokens can skip their prefill. Change one token near the start, and every key and value after it changes too, so nothing can be reused.

Finally, the script sizes the cache for two real model shapes:

```text
Llama 3.1 8B (32 layers, 8 KV heads, 128 dims): 128 KiB per token, 3.9 GiB for a 32k-token conversation
Llama 3.1 70B (80 layers, 8 KV heads, 128 dims): 320 KiB per token, 9.8 GiB for a 32k-token conversation
```

Per token, the cache stores a key and a value for every layer and every KV head: 2 x layers x KV heads x head size x 2 bytes at 16-bit precision. The [inference lesson](#w5-inference) uses the same formula for Llama 3 70B (327,680 bytes per token) and shows how serving engines pack thousands of these caches onto a GPU.

```viz
caption: One long conversation holds gigabytes of GPU memory while it waits for the user's next message. That memory is what limits how many users one GPU can serve.
<div class="vz-bars"><span>Llama 3.1 8B, 32k tokens</span><span class="bar sk"><i class="sk w" style="--w:40%"></i></span><b>3.9 GiB</b><span>Llama 3.1 70B, 32k tokens</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>9.8 GiB</b></div>
<div class="vz-src">2 x layers x KV heads x head size x 2 bytes, with shapes from the <a href="https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/MODEL_CARD.md">Llama 3.1 model card</a> and configs; output of <code>uv run python -m uth.kv_cache</code>.</div>
```

## What it changes in your designs

| Design decision | What attention and the cache explain | Where in the course |
|---|---|---|
| Ask for short answers | Each output token is one sequential decode step over the whole cache; halving output roughly halves generation time | [Primer](#primer), [inference](#w5-inference) |
| Stream responses | Prefill sets time to first token; streaming shows tokens as decode makes them, so users see progress | [Secure APIs](#w4-apis) |
| Put stable content first | Caches match prefixes: system prompt, tool definitions and long documents first, then the changing conversation | [Context engineering](#w1-context), [caching](#w5-scaling) |
| Never rewrite the prefix in a gateway | Re-serialising JSON or inserting a timestamp changes early tokens and destroys cache hits; Switchboard forwards bytes unchanged for this reason | [AI gateways](#w7-gateways) |
| Trim and summarise long sessions | Every turn re-reads the whole history: more cost, slower decode, and more cache memory on the server | [Agent memory](#w1-memory) |
| Self-hosting capacity | GPU memory for caches, not compute, usually caps concurrent users | [Inference](#w5-inference) |

> [!rule] Treat the prompt as an append-only log. Stable parts first, changing parts last, nothing early that differs between requests. Every design that respects this gets cheaper and faster for free.

## Go deeper

Raschka's book builds attention step by step in chapter 3, "Coding Attention Mechanisms", from a simplified version to causal multi-head attention; the free [chapter 3 notebooks](https://github.com/rasbt/LLMs-from-scratch/tree/main/ch03) contain all of it. His repository then adds a [KV cache to the chapter 4 GPT model](https://github.com/rasbt/LLMs-from-scratch/tree/main/ch04/03_kv-cache), and [grouped-query attention](https://github.com/rasbt/LLMs-from-scratch/tree/main/ch04/04_gqa), which is how Llama 3 gets to 8 KV heads. The original transformer paper is [Vaswani et al. (2017)](https://arxiv.org/abs/1706.03762).

```quiz
[
  {"q": "Why does a 400-token answer usually take longer than reading a 20,000-token prompt?", "options": ["Output tokens are bigger", "The prompt is processed in parallel during prefill, while output tokens are produced one sequential decode step at a time", "Providers slow down output on purpose", "The KV cache is empty during decode"], "answer": 1, "why": "Each output token depends on the previous one, so decode steps cannot run in parallel for one answer."},
  {"q": "Two requests share a 3,000-token system prompt, but one inserts the current time on line 1. Which benefits from prompt caching?", "options": ["Both equally", "Only the one without the timestamp; the timestamp changes early tokens, so every cached key and value after it is invalid", "Only the one with the timestamp", "Neither; caching works on embeddings"], "answer": 1, "why": "A cache holds keys and values for an exact token sequence at exact positions. Anything that differs early breaks the match for everything after it."},
  {"q": "A model has 32 layers, 8 KV heads and 128 dimensions per head at 16-bit precision. Roughly how much cache does one 32,000-token conversation hold?", "options": ["About 40 MB", "About 400 MB", "About 4 GB", "About 40 GB"], "answer": 2, "why": "2 x 32 x 8 x 128 x 2 bytes = 128 KiB per token; times 32,000 is about 3.9 GiB."}
]
```
