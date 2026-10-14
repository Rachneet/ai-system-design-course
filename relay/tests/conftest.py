import tempfile
from datetime import UTC, datetime
from uuid import uuid4

import pgserver
import pytest
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.db import Store
from app.embeddings import HashEmbedder
from app.ingest import reconcile, run_once
from app.retrieval import Retriever
from app.seed import seed
from app.tools import Context

NOW = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)

DATA = {
    "customers": [{"id": "c_77", "name": "Ada"}, {"id": "c_91", "name": "Grace"}],
    "orders": [
        {"id": 1042, "customer_id": "c_77", "status": "delivered", "total": 45.00, "days_ago": 6},
        {
            "id": 5520,
            "customer_id": "c_77",
            "status": "delivered",
            "total": 189.00,
            "days_ago": 52,
            "items": [
                {
                    "sku": "TENT-RDG-2P",
                    "name": "Ridgeline 2P tent",
                    "category": "tent",
                    "qty": 1,
                    "price": 189.0,
                    "used": True,
                }
            ],
        },
        {
            "id": 5521,
            "customer_id": "c_77",
            "status": "delivered",
            "total": 120.00,
            "days_ago": 45,
            "items": [
                {"sku": "JKT-ALP", "name": "Alpine jacket", "category": "apparel", "qty": 1, "price": 120.0}
            ],
        },
        {"id": 3001, "customer_id": "c_77", "status": "delivered", "total": 640.00, "days_ago": 10},
        {"id": 7001, "customer_id": "c_77", "status": "shipped", "total": 89.00, "eta_in_days": 3},
        {"id": 2210, "customer_id": "c_91", "status": "delivered", "total": 120.00, "days_ago": 3},
    ],
}


@pytest.fixture(scope="session")
def pg_url():
    srv = pgserver.get_server(tempfile.mkdtemp(), cleanup_mode="stop")
    srv.psql("CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;")
    yield srv.get_uri()
    srv.cleanup()


@pytest.fixture
async def store(pg_url):
    """A fresh schema per test on its own connection, so tests are isolated and can run in any order."""
    conn = await AsyncConnection.connect(pg_url, autocommit=True, row_factory=dict_row)
    schema = f"t_{uuid4().hex[:12]}"
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.execute(f"SET search_path TO {schema}, public")
    s = Store(conn)
    await s.apply_schema()
    await seed(s, DATA, NOW)
    yield s
    await conn.execute(f"DROP SCHEMA {schema} CASCADE")
    await conn.close()


@pytest.fixture
async def retriever(store):
    """The real kb/ folder indexed with the hashing embedder (no model download) and no reranker."""
    await reconcile(store)
    await run_once(store, HashEmbedder())
    return Retriever(store, HashEmbedder())


@pytest.fixture
def ctx(store, retriever):
    return Context(store=store, customer_id="c_77", session_id=None, now=NOW, retriever=retriever)
