---
id: uth-tokens
week: 98
kind: lesson
title: "Under the hood: how text becomes tokens"
short: Tokens from scratch
minutes: 35
summary: Build a byte-pair tokenizer in 80 lines and see why cost, limits, latency and even redaction are counted in tokens, and why the same request costs more in some languages.
---

## What this explains

Every number you budget in this course is counted in tokens: prices, context limits, rate limits in tokens per minute, output speed, the KV cache. The [primer](#primer) gave you the rule of thumb: about four characters, or three quarters of a word, per English token. This page shows where tokens come from, so that you can predict when that rule breaks. It breaks in ways that cost money.

You will build a byte-pair encoding (BPE) tokenizer, the family most current models use, and run it on the same support request in three languages.

## The idea: start from bytes, merge what is common

A tokenizer has to turn *any* string into numbers the model knows. BPE starts from the 256 possible byte values, so nothing is ever unknown: an emoji, a typo or a language the designers never considered is still a sequence of bytes. Then it learns shortcuts. It counts every adjacent pair of symbols in a training corpus, merges the most frequent pair into a new symbol, and repeats until the vocabulary reaches its target size.

```viz
caption: BPE starts from bytes and keeps merging the most common neighbouring pair. Frequent text becomes few tokens; rare text stays close to one token per byte.
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk"><h5>Start: bytes</h5><div class="vz-row"><span class="ch sk">r</span><span class="ch sk">e</span><span class="ch sk">f</span><span class="ch sk">u</span><span class="ch sk">n</span><span class="ch sk">d</span></div><p>6 tokens</p></div>
  <div class="vz-panel sk c"><h5>After early merges</h5><div class="vz-row"><span class="ch sk c">re</span><span class="ch sk c">fu</span><span class="ch sk c">nd</span></div><p>3 tokens</p></div>
  <div class="vz-panel sk g"><h5>After many merges</h5><div class="vz-row"><span class="ch sk g">refund</span></div><p>1 token, if the corpus said it often</p></div>
</div>
```

Encoding new text replays the merges in the order they were learned. Decoding concatenates the bytes each token stands for. That is the whole algorithm; production tokenizers add rules (split on spaces and digits first, special tokens for roles and tools) and vocabularies of 100,000 to 250,000 tokens, but not a new idea.

## Run it

The companion code is in [`under-the-hood/`](https://github.com/Rachneet/ai-system-design-course/tree/main/under-the-hood) in the course repository. It needs only Python and numpy.

```bash
cd under-the-hood && uv sync
uv run python -m uth.bpe
```

The script trains 256 merges on about 10,000 characters of English support messages, then encodes the same request in English, German and Hindi:

```text
How the first sentence is split:
My |  order |  a | r | r | ive | d  | da | ma | g | ed | .  | C | a | n  | you |  refun | d  | i | t |  to my |  car | d | ?

language   chars  bytes  tokens  chars per token
English       55     55      24             2.29
German        84     86      73             1.15
Hindi         74    190     190             0.39
```

Three things to notice:

- **Common phrases collapse.** `" to my"` and `" order"` are single tokens, because the corpus said them often. `"arrived"` did not appear as often, so it stays in pieces.
- **German costs about three times as many tokens** for the same meaning: longer words, and merges that were learned on English.
- **Hindi costs one token per byte.** Devanagari takes three bytes per character in UTF-8, and this tokenizer learned no merges for it, so every byte is a token.

A real tokenizer trained on many languages narrows these gaps but does not close them. [Petrov et al.](https://arxiv.org/abs/2305.15425) measured commercial tokenizers and found that the same text "can have drastically different tokenization lengths, with differences up to 15 times in some cases".

```viz
caption: The same refund request, tokenized by a tokenizer that learned only English. Less-seen languages pay more for the same meaning.
<div class="vz-bars"><span>English</span><span class="bar sk"><i class="sk g" style="--w:13%"></i></span><b>24 tokens</b><span>German</span><span class="bar sk"><i class="sk w" style="--w:38%"></i></span><b>73 tokens</b><span>Hindi</span><span class="bar sk"><i class="sk b" style="--w:100%"></i></span><b>190 tokens</b></div>
<div class="vz-src">Output of <code>uv run python -m uth.bpe</code> in the course repository: a 512-token vocabulary trained on English support text.</div>
```

## What it changes in your designs

| Design decision | What tokens explain | Where in the course |
|---|---|---|
| Cost per conversation | Bills are per token, so a desk serving German or Hindi speakers costs more per conversation than the English pilot predicted. Measure token counts on real traffic in every language before you set budgets | [AI FinOps](#w10-finops), [cost per turn](#w5-monitoring) |
| Context and rate limits | A context window or a tokens-per-minute limit holds less text in some languages. A limit sized on English traffic throttles other tenants first | [Multi-tenancy](#w9-tenancy) |
| Latency | Output time is output tokens divided by output speed, so the same answer is slower in a language that tokenizes poorly | [LLM inference](#w5-inference) |
| Chunking for retrieval | Chunk by tokens, not characters, or chunk sizes vary by language | [Scalable search](#w2-search) |
| Prompt caching | A cache hit needs the same *tokens*. A change in whitespace or punctuation early in a prompt changes its tokens, and with them everything after | [Caching](#w5-scaling) |
| Counting before you send | Use the provider's token-counting endpoint or tokenizer library, not a characters-divided-by-four estimate, when a request is near a limit | [Primer](#primer) |

> [!rule] Estimate in tokens, measured on your own traffic, per language. Characters divided by four is an estimate for English prose and nothing else; code, numbers, JSON and most other languages tokenize differently.

## Go deeper

Sebastian Raschka's [*Build a Large Language Model (From Scratch)*](http://mng.bz/orYv) covers this in chapter 2, "Working with Text Data". The free code is in his repository: the [chapter 2 notebooks](https://github.com/rasbt/LLMs-from-scratch/tree/main/ch02), and a step-by-step [BPE tokenizer from scratch](https://github.com/rasbt/LLMs-from-scratch/blob/main/ch02/05_bpe-from-scratch/bpe-from-scratch-simple.ipynb) that goes further than this page, including the pre-tokenization rules real tokenizers use. The original idea for subword units comes from [Sennrich et al. (2016)](https://arxiv.org/abs/1508.07909).

```quiz
[
  {"q": "Why can a byte-level BPE tokenizer encode any string, including emoji and languages it never saw?", "options": ["It has a token for every Unicode character", "Its base vocabulary is the 256 byte values, so any text is at worst one token per byte", "It falls back to an UNKNOWN token", "It translates text to English first"], "answer": 1, "why": "Merges are shortcuts on top of bytes. Text the merges do not cover still encodes, one byte per token."},
  {"q": "Your English pilot used 1,200 tokens per conversation. You launch in Hindi with the same flows. What should you expect?", "options": ["About 1,200 tokens", "Fewer tokens, because Hindi is concise", "Possibly several times more tokens, so measure before setting budgets and rate limits", "The provider normalises cost across languages"], "answer": 2, "why": "Tokenizers trained mostly on English compress other languages less well; measured gaps reach 15 times in some cases."},
  {"q": "A team adds a space to the start of its 4,000-token system prompt. What happens to prompt caching?", "options": ["Nothing; caching ignores whitespace", "Only the first token changes", "The cached prefix no longer matches, so the whole prompt is processed and billed as uncached until the cache is rebuilt", "Caching gets faster"], "answer": 2, "why": "Caches match exact token sequences from the start. A change at the start changes the tokens, and the cached keys and values no longer apply."}
]
```
