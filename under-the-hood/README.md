# Under the hood: five small models of what happens inside an LLM

Companion code for the course's optional [Under the hood](../content/98-01-tokens.md) lessons. Each module builds
one mechanism from scratch in numpy, runs in about a second on a laptop, and prints the numbers its lesson discusses.
Each lesson then turns those numbers into a system design decision.

| Module | Builds | Explains | Lesson |
|---|---|---|---|
| `uth.bpe` | A byte-pair encoding tokenizer | Why cost and limits are counted in tokens, and why some languages cost more | [Tokens](../content/98-01-tokens.md) |
| `uth.kv_cache` | A tiny decoder with and without a KV cache, and a reused prefix | Why output length drives latency, why prompt caching works, what long contexts cost in memory | [Attention](../content/98-02-attention.md) |
| `uth.sampling` | Temperature, top-p, pass@k and pass^k | Why the same prompt gives different answers, and why agents are gated on pass^k | [Sampling](../content/98-03-sampling.md) |
| `uth.lora` | LoRA adapters trained by gradient descent, merged, and swapped per tenant | When to fine-tune, and why adapters are per tenant and chosen by the gateway | [LoRA](../content/98-04-lora.md) |
| `uth.test_time` | Voting over samples, reasoning latency, routing by difficulty | When thinking longer pays, and how to route | [Reasoning](../content/98-05-reasoning.md) |

```bash
uv sync
uv run python -m uth.bpe        # or kv_cache, sampling, lora, test_time
uv run pytest                   # 7 tests: each module does what its lesson claims
```

These are teaching models: random weights, toy data, and illustrative inputs that are labelled as such. For the
full treatment in PyTorch, read Sebastian Raschka's
[LLMs-from-scratch](https://github.com/rasbt/LLMs-from-scratch) and
[reasoning-from-scratch](https://github.com/rasbt/reasoning-from-scratch), the code for his books
*Build a Large Language Model (From Scratch)* and *Build a Reasoning Model (From Scratch)*. This code is written
independently for this course and does not copy his.
