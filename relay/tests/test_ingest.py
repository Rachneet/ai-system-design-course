import shutil

import pytest

from app import ingest
from app.embeddings import HashEmbedder
from app.ingest import KB_DIR, chunk, parse, reconcile, run_once, sync_document


class CountingEmbedder(HashEmbedder):
    def __init__(self):
        self.texts: list[str] = []

    async def embed(self, texts):
        self.texts += texts
        return await super().embed(texts)


class BrokenEmbedder(HashEmbedder):
    async def embed(self, texts):
        raise RuntimeError("embedding API is down")


@pytest.fixture
def kb(tmp_path):
    for name in ("POL-RETURNS-2026.md", "INT-REFUND-FRAUD.md"):
        shutil.copy(KB_DIR / name, tmp_path / name)
    return tmp_path


async def count(store, sql):
    async with store.conn() as c:
        return (await (await c.execute(sql)).fetchone())["n"]


def test_front_matter_and_stable_chunk_ids(kb):
    doc = parse(kb / "INT-REFUND-FRAUD.md")
    assert doc.acl == ["group:support"] and doc.title.startswith("Internal")
    assert [c.chunk_id for c in chunk(doc)] == [c.chunk_id for c in chunk(parse(kb / "INT-REFUND-FRAUD.md"))]
    returns = chunk(parse(kb / "POL-RETURNS-2026.md"))
    assert [c.context for c in returns] == [
        "Returns policy 2026 > Return windows",
        "Returns policy 2026 > Refund timing and fees",
        "Returns policy 2026 > Exclusions",
    ]


async def test_edit_reembeds_only_the_changed_chunk(store, kb):
    emb = CountingEmbedder()
    first = await sync_document(store, emb, parse(kb / "POL-RETURNS-2026.md"))
    assert first.added == 3 and len(emb.texts) == 3
    assert (await sync_document(store, emb, parse(kb / "POL-RETURNS-2026.md"))).skipped

    path = kb / "POL-RETURNS-2026.md"
    path.write_text(path.read_text().replace("3 to 5 business days", "2 to 4 business days"))
    emb.texts.clear()
    edit = await sync_document(store, emb, parse(path))
    assert (edit.added, edit.removed) == (1, 1) and len(emb.texts) == 1 and "2 to 4" in emb.texts[0]
    assert await count(store, "SELECT count(*) AS n FROM chunks WHERE doc_id = 'POL-RETURNS-2026'") == 3


async def test_acl_change_needs_no_embedding(store, kb):
    emb = CountingEmbedder()
    path = kb / "INT-REFUND-FRAUD.md"
    await sync_document(store, emb, parse(path))
    path.write_text(path.read_text().replace("acl: group:support", "acl: group:support, group:fraud"))
    emb.texts.clear()
    result = await sync_document(store, emb, parse(path))
    assert (result.added, result.removed, emb.texts) == (0, 0, [])
    async with store.conn() as c:
        acl = (
            await (await c.execute("SELECT acl FROM documents WHERE doc_id = 'INT-REFUND-FRAUD'")).fetchone()
        )["acl"]
    assert acl == ["group:support", "group:fraud"]


async def test_reconcile_and_worker_handle_new_and_deleted_files(store, kb):
    assert await reconcile(store, kb) == 2
    assert await run_once(store, HashEmbedder()) == 2
    assert await reconcile(store, kb) == 0  # nothing changed
    (kb / "POL-RETURNS-2026.md").unlink()
    assert await reconcile(store, kb) == 1
    await run_once(store, HashEmbedder())
    assert await count(store, "SELECT count(*) AS n FROM chunks WHERE doc_id = 'POL-RETURNS-2026'") == 0
    assert await count(store, "SELECT count(*) AS n FROM documents WHERE deleted_at IS NOT NULL") == 1


async def test_failing_jobs_retry_then_dead_letter(store, kb, monkeypatch):
    monkeypatch.setattr(ingest, "MAX_ATTEMPTS", 2)
    await reconcile(store, kb)
    for _ in range(3):
        await run_once(store, BrokenEmbedder())
        async with store.conn() as c:
            await c.execute(
                "UPDATE ingest_jobs SET run_after = now() WHERE status = 'queued'"
            )  # skip the backoff wait
    assert await count(store, "SELECT count(*) AS n FROM ingest_jobs WHERE status = 'dead'") == 2
    async with store.conn() as c:
        errors = await (await c.execute("SELECT last_error FROM ingest_jobs")).fetchall()
    assert all("embedding failed" in e["last_error"] for e in errors)
