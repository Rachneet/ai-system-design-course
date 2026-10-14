"""Embedding and reranking models behind small interfaces, so tests use a fast deterministic stand-in."""

import asyncio
import hashlib
import math
import re
from typing import Protocol

DIM = 384  # matches vector(384) in schema.sql


class Embedder(Protocol):
    name: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...


class Reranker(Protocol):
    async def scores(self, query: str, docs: list[str]) -> list[float]: ...


class LocalEmbedder:
    """BAAI/bge-small-en-v1.5 via fastembed: runs on CPU, no API key, about 130 MB download on first use."""

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5"):
        from fastembed import TextEmbedding

        self.name = model
        self.model = TextEmbedding(model)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(lambda: [v.tolist() for v in self.model.passage_embed(texts)])

    async def embed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(lambda: next(iter(self.model.query_embed(text))).tolist())


class LocalReranker:
    """A small cross-encoder (MiniLM trained on MS MARCO) that reads query and passage together."""

    def __init__(self, model: str = "Xenova/ms-marco-MiniLM-L-6-v2"):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.model = TextCrossEncoder(model)

    async def scores(self, query: str, docs: list[str]) -> list[float]:
        return await asyncio.to_thread(lambda: list(self.model.rerank(query, docs)))


class HashEmbedder:
    """Deterministic bag-of-words hashing into DIM buckets. Lexical, not semantic: for tests only."""

    name = "hash-bow-384"

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * DIM
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            v[h % DIM] += 1.0 if (h >> 9) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


def to_pgvector(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"
