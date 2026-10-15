"""Attention and the KV cache, from scratch in numpy: why output length drives latency and why prompt caching works.

A decoder makes one token per forward pass. Each new token attends to every earlier token's keys and values (K, V).
Without a cache, every step recomputes K and V for the whole sequence; with a cache, it computes them once per token
and appends. Same answer, far less work, paid for in memory. A cached prefix (a system prompt) can be reused by any
request that starts with exactly the same tokens: that is what provider prompt caching sells.

    uv run python -m uth.kv_cache
"""

import time
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Config:
    vocab: int = 64
    d: int = 64
    heads: int = 4
    layers: int = 2
    seed: int = 0


def norm(x):
    return (x - x.mean(-1, keepdims=True)) / np.sqrt(x.var(-1, keepdims=True) + 1e-5)


def softmax(x):
    x = x - x.max(-1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(-1, keepdims=True)


@dataclass
class Cache:
    """Per layer, the keys and values of every token seen so far: (heads, tokens, head_dim)."""

    k: list = field(default_factory=list)
    v: list = field(default_factory=list)

    def tokens(self) -> int:
        return self.k[0].shape[1] if self.k else 0

    def copy(self) -> "Cache":
        return Cache([a.copy() for a in self.k], [a.copy() for a in self.v])


class TinyDecoder:
    def __init__(self, cfg: Config | None = None):
        cfg = cfg or Config()
        self.cfg, rng = cfg, np.random.default_rng(cfg.seed)
        d, s = cfg.d, 1 / np.sqrt(cfg.d)
        self.emb = rng.normal(0, 1, (cfg.vocab, d))
        self.pos = rng.normal(0, 0.1, (512, d))
        self.w = [
            {
                name: rng.normal(0, s, shape)
                for name, shape in (
                    ("q", (d, d)),
                    ("k", (d, d)),
                    ("v", (d, d)),
                    ("o", (d, d)),
                    ("up", (d, 4 * d)),
                    ("down", (4 * d, d)),
                )
            }
            for _ in range(cfg.layers)
        ]
        self.out = rng.normal(0, s, (d, cfg.vocab))
        self.attn_dot_products = 0  # q.k scores computed, a proxy for attention work

    def split(self, x):  # (t, d) -> (heads, t, head_dim)
        t = x.shape[0]
        return x.reshape(t, self.cfg.heads, -1).transpose(1, 0, 2)

    def forward(self, ids: list[int], start: int, cache: Cache | None) -> np.ndarray:
        """Run `ids` (positions start..) through the model. With a cache, only these tokens are computed; their K and
        V are appended so later tokens can attend to them. Returns logits for the last token."""
        x = self.emb[ids] + self.pos[start : start + len(ids)]
        for i, w in enumerate(self.w):
            h = norm(x)
            q, k, v = self.split(h @ w["q"]), self.split(h @ w["k"]), self.split(h @ w["v"])
            if cache is not None:
                if len(cache.k) <= i:
                    cache.k.append(k), cache.v.append(v)
                else:
                    cache.k[i] = np.concatenate([cache.k[i], k], axis=1)
                    cache.v[i] = np.concatenate([cache.v[i], v], axis=1)
                k, v = cache.k[i], cache.v[i]
            scores = q @ k.transpose(0, 2, 1) / np.sqrt(q.shape[-1])  # (heads, new tokens, all tokens)
            self.attn_dot_products += scores.size
            total, new = k.shape[1], len(ids)
            mask = np.arange(total)[None, :] > (np.arange(new)[:, None] + total - new)  # no peeking ahead
            scores = np.where(mask, -1e9, scores)
            a = (softmax(scores) @ v).transpose(1, 0, 2).reshape(new, -1)
            x = x + a @ w["o"]
            x = x + np.maximum(0, norm(x) @ w["up"]) @ w["down"]
        return norm(x[-1]) @ self.out

    def generate(self, prompt: list[int], n: int, use_cache: bool, cache: Cache | None = None) -> list[int]:
        ids = list(prompt)
        if not use_cache:
            for _ in range(n):  # every step reprocesses the whole sequence
                ids.append(int(self.forward(ids, 0, None).argmax()))
            return ids[len(prompt) :]
        cache = cache.copy() if cache is not None else Cache()
        done = cache.tokens()
        logits = self.forward(ids[done:], done, cache)  # prefill: the uncached part of the prompt, in parallel
        for _ in range(n):  # decode: one token per step, attending to the cache
            ids.append(int(logits.argmax()))
            logits = self.forward([ids[-1]], len(ids) - 1, cache)
        return ids[len(prompt) :]


def kv_bytes_per_token(layers: int, kv_heads: int, head_dim: int, bytes_per_value: int = 2) -> int:
    """K and V, for every layer and KV head: 2 x layers x kv_heads x head_dim x bytes."""
    return 2 * layers * kv_heads * head_dim * bytes_per_value


def main() -> None:
    m = TinyDecoder()
    prompt, n = list(range(1, 41)), 200

    for use_cache in (False, True):
        m.attn_dot_products = 0
        t0 = time.perf_counter()
        out = m.generate(prompt, n, use_cache)
        ms = (time.perf_counter() - t0) * 1000
        label = "with KV cache" if use_cache else "no cache     "
        print(f"{label}: {ms:7.1f} ms, {m.attn_dot_products:>11,} attention scores, first tokens {out[:6]}")
    print("Identical tokens; the cache turns quadratic recomputation into one new row per step.\n")

    system = list(range(1, 33))  # a shared system prompt
    prefix = Cache()
    m.forward(system, 0, prefix)
    for user in ([40, 41, 42], [50, 51]):
        a = m.generate(system + user, 5, True, cache=prefix)  # prefill only the user's tokens
        b = m.generate(system + user, 5, True)  # prefill everything
        print(f"user turn {user}: reused {prefix.tokens()} cached tokens, same output: {a == b}")
    changed = [99] + system[1:]
    print(
        f"change the first token and nothing can be reused: the cache holds K, V for {system[:3]}..., "
        f"not for {changed[:3]}...\n"
    )

    for name, shape in (
        ("Llama 3.1 8B (32 layers, 8 KV heads, 128 dims)", (32, 8, 128)),
        ("Llama 3.1 70B (80 layers, 8 KV heads, 128 dims)", (80, 8, 128)),
    ):
        per = kv_bytes_per_token(*shape)
        print(f"{name}: {per / 1024:.0f} KiB per token, {per * 32_000 / 2**30:.1f} GiB for a 32k-token conversation")


if __name__ == "__main__":
    main()
