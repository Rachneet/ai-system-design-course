"""Ingestion: parse, chunk, embed only what changed, and keep the index in sync with the source folder.

uv run python -m app.ingest reconcile   # enqueue upserts/deletes by diffing kb/ against the index
uv run python -m app.ingest work        # run a worker until interrupted
uv run python -m app.ingest sync        # reconcile, then drain the queue once (handy locally)
"""

import asyncio
import hashlib
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .db import Store
from .embeddings import Embedder, to_pgvector

KB_DIR = Path(__file__).parent.parent / "kb"
MAX_CHARS = 1800  # roughly 400 to 500 tokens
MAX_ATTEMPTS = 5


class TransientError(Exception):
    """Worth retrying: rate limits, timeouts, a briefly unavailable model."""


@dataclass
class Doc:
    doc_id: str
    title: str
    acl: list[str]
    body: str
    content_hash: str
    source_path: str


@dataclass
class Chunk:
    chunk_id: str
    ord: int
    context: str
    content: str


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def parse(path: Path) -> Doc:
    raw = path.read_text(encoding="utf-8")
    meta, body = {}, raw
    if m := re.match(r"^---\n(.*?)\n---\n", raw, re.DOTALL):
        meta = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
        meta = {k.strip(): v.strip() for k, v in meta.items()}
        body = raw[m.end() :]
    acl = [p.strip() for p in meta.get("acl", "public").split(",") if p.strip()]
    return Doc(path.stem, meta.get("title", path.stem), acl, body.strip(), sha(raw), str(path))


def chunk(doc: Doc) -> list[Chunk]:
    """Split on '## ' headings, then on paragraphs if a section is too long. IDs come from the text itself."""
    sections, heading, buf = [], None, []
    for line in doc.body.splitlines():
        if line.startswith("## "):
            if buf:
                sections.append((heading, "\n".join(buf).strip()))
            heading, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if buf:
        sections.append((heading, "\n".join(buf).strip()))

    pieces = []
    for heading, text in sections:
        if not text:
            continue
        context = f"{doc.title} > {heading}" if heading else doc.title
        part = ""
        for para in re.split(r"\n\s*\n", text):
            if part and len(part) + len(para) > MAX_CHARS:
                pieces.append((context, part.strip()))
                part = ""
            part += para + "\n\n"
        if part.strip():
            pieces.append((context, part.strip()))

    out, seen = [], set()
    for i, (context, content) in enumerate(pieces):
        cid = f"{doc.doc_id}#{sha(context + content)[:12]}"
        if cid in seen:  # identical text twice in one document
            cid = f"{cid}-{i}"
        seen.add(cid)
        out.append(Chunk(cid, i, context, content))
    return out


@dataclass
class SyncResult:
    added: int
    removed: int
    skipped: bool = False


async def sync_document(store: Store, embedder: Embedder, doc: Doc) -> SyncResult:
    new = {c.chunk_id: c for c in chunk(doc)}
    async with store.conn() as c:
        row = await (
            await c.execute("SELECT content_hash, deleted_at FROM documents WHERE doc_id = %s", (doc.doc_id,))
        ).fetchone()
        if row and row["content_hash"] == doc.content_hash and row["deleted_at"] is None:
            return SyncResult(0, 0, skipped=True)
        existing = {
            r["chunk_id"]
            for r in await (
                await c.execute("SELECT chunk_id FROM chunks WHERE doc_id = %s", (doc.doc_id,))
            ).fetchall()
        }

    to_add = [new[i] for i in new if i not in existing]
    to_remove = sorted(existing - new.keys())
    try:
        vectors = await embedder.embed([f"{ch.context}\n{ch.content}" for ch in to_add]) if to_add else []
    except Exception as e:
        raise TransientError(f"embedding failed: {e!r}") from e

    async with store.conn() as c, c.transaction():  # readers see the old version or the new one, never a mix
        await c.execute(
            "INSERT INTO documents (doc_id, title, source_path, content_hash, acl) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (doc_id) DO UPDATE SET title = EXCLUDED.title, source_path = EXCLUDED.source_path, "
            "content_hash = EXCLUDED.content_hash, acl = EXCLUDED.acl, updated_at = now(), deleted_at = NULL",
            (doc.doc_id, doc.title, doc.source_path, doc.content_hash, doc.acl),
        )
        if to_remove:
            await c.execute("DELETE FROM chunks WHERE chunk_id = ANY(%s)", (to_remove,))
        async with c.cursor() as cur:
            await cur.executemany(
                "INSERT INTO chunks (chunk_id, doc_id, ord, context, content, embedding, embed_model) "
                "VALUES (%s, %s, %s, %s, %s, %s::vector, %s)",
                [
                    (ch.chunk_id, doc.doc_id, ch.ord, ch.context, ch.content, to_pgvector(v), embedder.name)
                    for ch, v in zip(to_add, vectors, strict=True)
                ],
            )
        # Unchanged chunks keep their vectors; only their order may have moved.
        for ch in new.values():
            if ch.chunk_id in existing:
                await c.execute("UPDATE chunks SET ord = %s WHERE chunk_id = %s", (ch.ord, ch.chunk_id))
    return SyncResult(len(to_add), len(to_remove))


async def delete_document(store: Store, doc_id: str) -> None:
    async with store.conn() as c, c.transaction():
        await c.execute("DELETE FROM chunks WHERE doc_id = %s", (doc_id,))
        await c.execute("UPDATE documents SET deleted_at = now() WHERE doc_id = %s", (doc_id,))


# ---- job queue (Postgres, SELECT ... FOR UPDATE SKIP LOCKED) ------------------------------------
CLAIM = """
UPDATE ingest_jobs SET status = 'running', attempts = attempts + 1
WHERE id = (
  SELECT id FROM ingest_jobs WHERE status = 'queued' AND run_after <= now()
  ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1
)
RETURNING id, doc_path, op, attempts
"""


async def enqueue(store: Store, doc_path: str, op: str) -> None:
    async with store.conn() as c:
        await c.execute("INSERT INTO ingest_jobs (doc_path, op) VALUES (%s, %s)", (doc_path, op))


async def process(store: Store, embedder: Embedder, doc_path: str, op: str) -> None:
    path = Path(doc_path)
    if (
        op == "delete" or not path.exists()
    ):  # read the file at processing time, so we always index its latest state
        await delete_document(store, path.stem)
    else:
        await sync_document(store, embedder, parse(path))


async def run_once(store: Store, embedder: Embedder, max_jobs: int = 1000) -> int:
    """Process queued jobs until the queue is empty. Returns the number processed."""
    done = 0
    while done < max_jobs:
        async with store.conn() as c:
            job = await (await c.execute(CLAIM)).fetchone()
        if job is None:
            return done
        try:
            await process(store, embedder, job["doc_path"], job["op"])
            status, error, delay = "done", None, 0.0
        except Exception as e:  # noqa: BLE001 - a poison document must not kill the worker
            retryable = isinstance(e, TransientError) and job["attempts"] < MAX_ATTEMPTS
            status = "queued" if retryable else "dead"
            error, delay = repr(e)[:500], min(300, 2 ** job["attempts"]) + random.random()
        async with store.conn() as c:
            await c.execute(
                "UPDATE ingest_jobs SET status = %s, last_error = %s, run_after = now() + make_interval(secs => %s) "
                "WHERE id = %s",
                (status, error, delay, job["id"]),
            )
        done += 1
    return done


async def reconcile(store: Store, kb_dir: Path = KB_DIR) -> int:
    """Diff the folder against the index and enqueue what changed. The safety net for missed change events."""
    files = {p.stem: p for p in kb_dir.glob("*.md")}
    async with store.conn() as c:
        rows = await (await c.execute("SELECT doc_id, content_hash, deleted_at FROM documents")).fetchall()
    indexed = {r["doc_id"]: r for r in rows}
    jobs = 0
    for doc_id, path in files.items():
        r = indexed.get(doc_id)
        if (
            r is None
            or r["deleted_at"] is not None
            or r["content_hash"] != sha(path.read_text(encoding="utf-8"))
        ):
            await enqueue(store, str(path), "upsert")
            jobs += 1
    for doc_id, r in indexed.items():
        if doc_id not in files and r["deleted_at"] is None:
            await enqueue(store, str(kb_dir / f"{doc_id}.md"), "delete")
            jobs += 1
    return jobs


async def main(cmd: str) -> None:
    from .config import settings
    from .db import open_pool
    from .embeddings import LocalEmbedder

    pool = await open_pool(settings.database_url)
    store = Store(pool)
    await store.apply_schema()
    embedder = LocalEmbedder()
    if cmd in ("reconcile", "sync"):
        print(f"enqueued {await reconcile(store)} jobs")
    if cmd == "sync":
        print(f"processed {await run_once(store, embedder)} jobs")
    if cmd == "work":
        while True:
            if not await run_once(store, embedder):
                await asyncio.sleep(1)
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "sync"))
