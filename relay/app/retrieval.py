"""Hybrid retrieval: full-text and vector search, fused with RRF, then reranked. Access control is applied in SQL,
before anything reaches the model."""

import re
from dataclasses import dataclass

from .db import Store
from .embeddings import Embedder, Reranker, to_pgvector

RRF_K = 60
STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "for",
    "of",
    "to",
    "my",
    "is",
    "it",
    "in",
    "on",
    "do",
    "i",
    "you",
    "can",
    "how",
    "what",
    "with",
    "does",
    "are",
    "be",
    "me",
    "your",
    "if",
    "at",
    "by",
    "from",
}

VISIBLE = "JOIN documents d USING (doc_id) WHERE d.deleted_at IS NULL AND d.acl && %(principals)s::text[]"


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    context: str
    content: str
    score: float


def principals_for(customer_id: str, staff: bool = False) -> list[str]:
    return ["public", f"user:{customer_id}"] + (["group:support"] if staff else [])


def or_query(text: str) -> str | None:
    """'return window used tent' -> 'return | window | used | tent' (OR, unlike websearch_to_tsquery's AND)."""
    terms = [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]
    return " | ".join(dict.fromkeys(terms)) or None


def rrf(*ranked: list[str], k: int = RRF_K) -> list[str]:
    scores: dict[str, float] = {}
    for ids in ranked:
        for rank, cid in enumerate(ids, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=scores.get, reverse=True)


class Retriever:
    def __init__(
        self, store: Store, embedder: Embedder, reranker: Reranker | None = None, candidates: int = 40
    ):
        self.store, self.embedder, self.reranker, self.candidates = store, embedder, reranker, candidates

    async def vector_ids(self, query: str, principals: list[str]) -> list[str]:
        vec = to_pgvector(await self.embedder.embed_query(query))
        async with self.store.conn() as c:
            rows = await (
                await c.execute(
                    f"SELECT chunk_id FROM chunks {VISIBLE} ORDER BY embedding <=> %(vec)s::vector LIMIT %(n)s",
                    {"principals": principals, "vec": vec, "n": self.candidates},
                )
            ).fetchall()
        return [r["chunk_id"] for r in rows]

    async def lexical_ids(self, query: str, principals: list[str]) -> list[str]:
        q = or_query(query)
        if q is None:
            return []
        async with self.store.conn() as c:
            rows = await (
                await c.execute(
                    f"SELECT chunk_id FROM chunks {VISIBLE} AND tsv @@ to_tsquery('english', %(q)s) "
                    "ORDER BY ts_rank_cd(tsv, to_tsquery('english', %(q)s)) DESC LIMIT %(n)s",
                    {"principals": principals, "q": q, "n": self.candidates},
                )
            ).fetchall()
        return [r["chunk_id"] for r in rows]

    async def fetch(self, ids: list[str]) -> list[Hit]:
        if not ids:
            return []
        async with self.store.conn() as c:
            rows = await (
                await c.execute(
                    "SELECT chunk_id, doc_id, context, content FROM chunks WHERE chunk_id = ANY(%s)", (ids,)
                )
            ).fetchall()
        by_id = {r["chunk_id"]: r for r in rows}
        return [
            Hit(i, by_id[i]["doc_id"], by_id[i]["context"], by_id[i]["content"], 0.0)
            for i in ids
            if i in by_id
        ]

    async def search(
        self, query: str, principals: list[str], k: int = 6, mode: str = "hybrid+rerank"
    ) -> list[Hit]:
        """mode: vector | lexical | hybrid | hybrid+rerank"""
        if mode == "vector":
            ids = await self.vector_ids(query, principals)
        elif mode == "lexical":
            ids = await self.lexical_ids(query, principals)
        else:
            ids = rrf(await self.lexical_ids(query, principals), await self.vector_ids(query, principals))
        if mode != "hybrid+rerank" or self.reranker is None:
            hits = await self.fetch(ids[:k])
            for i, h in enumerate(hits):
                h.score = 1.0 / (i + 1)
            return hits
        hits = await self.fetch(ids[: self.candidates])
        scores = await self.reranker.scores(query, [f"{h.context}\n{h.content}" for h in hits])
        for h, s in zip(hits, scores, strict=True):
            h.score = float(s)
        return sorted(hits, key=lambda h: h.score, reverse=True)[:k]
