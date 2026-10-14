"""Postgres access. Every customer-facing read is scoped by customer_id in SQL, never by the model."""

from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

SCHEMA = (Path(__file__).parent / "schema.sql").read_text()


class NotFound(Exception):
    pass


async def open_pool(url: str, max_size: int = 10) -> AsyncConnectionPool:
    pool = AsyncConnectionPool(
        url, min_size=1, max_size=max_size, open=False, kwargs={"row_factory": dict_row, "autocommit": True}
    )
    await pool.open()
    return pool


class Store:
    """Repository over either a pool (the API) or one connection (an isolated eval or test schema)."""

    def __init__(self, source: AsyncConnectionPool | AsyncConnection):
        self.source = source

    @asynccontextmanager
    async def conn(self):
        if isinstance(self.source, AsyncConnectionPool):
            async with self.source.connection() as c:
                yield c
        else:
            yield self.source

    async def apply_schema(self) -> None:
        async with self.conn() as c:
            await c.execute(SCHEMA)

    # ---- orders and refunds -------------------------------------------------------------------
    async def fetch_order(self, order_id: int, customer_id: str) -> dict | None:
        async with self.conn() as c:
            cur = await c.execute(
                "SELECT * FROM orders WHERE id = %s AND customer_id = %s", (order_id, customer_id)
            )
            return await cur.fetchone()

    async def list_orders(self, customer_id: str, limit: int = 10) -> list[dict]:
        async with self.conn() as c:
            cur = await c.execute(
                "SELECT id, status, total, delivered_at, eta FROM orders WHERE customer_id = %s "
                "ORDER BY id DESC LIMIT %s",
                (customer_id, limit),
            )
            return await cur.fetchall()

    async def refund_for(self, order_id: int) -> dict | None:
        async with self.conn() as c:
            cur = await c.execute("SELECT * FROM refunds WHERE order_id = %s", (order_id,))
            return await cur.fetchone()

    async def create_refund(self, order_id: int, amount: float, reason: str) -> bool:
        """Returns False if this order was already refunded (the unique key makes retries harmless)."""
        async with self.conn() as c:
            cur = await c.execute(
                "INSERT INTO refunds (order_id, amount, reason) VALUES (%s, %s, %s) "
                "ON CONFLICT (order_id) DO NOTHING RETURNING id",
                (order_id, amount, reason),
            )
            return await cur.fetchone() is not None

    async def create_approval(
        self, order_id: int, amount: float, reason: str, session_id: UUID | None
    ) -> int:
        async with self.conn() as c:
            cur = await c.execute(
                "INSERT INTO approvals (order_id, amount, reason, session_id) VALUES (%s, %s, %s, %s) RETURNING id",
                (order_id, amount, reason, session_id),
            )
            return (await cur.fetchone())["id"]

    async def create_escalation(self, customer_id: str, session_id: UUID | None, reason: str) -> int:
        async with self.conn() as c:
            cur = await c.execute(
                "INSERT INTO escalations (customer_id, session_id, reason) VALUES (%s, %s, %s) RETURNING id",
                (customer_id, session_id, reason),
            )
            return (await cur.fetchone())["id"]

    # ---- sessions -----------------------------------------------------------------------------
    async def load_session(self, session_id: UUID, customer_id: str, create: bool = False) -> list[dict]:
        """Returns the message history. A session owned by someone else looks exactly like a missing one."""
        async with self.conn() as c:
            cur = await c.execute("SELECT customer_id FROM sessions WHERE id = %s", (session_id,))
            row = await cur.fetchone()
            if row is None:
                if not create:
                    raise NotFound(session_id)
                await c.execute(
                    "INSERT INTO sessions (id, customer_id) VALUES (%s, %s)", (session_id, customer_id)
                )
                return []
            if row["customer_id"] != customer_id:
                raise NotFound(session_id)
            cur = await c.execute(
                "SELECT role, content FROM messages WHERE session_id = %s ORDER BY seq", (session_id,)
            )
            return [{"role": r["role"], "content": r["content"]} for r in await cur.fetchall()]

    async def append_messages(self, session_id: UUID, start_seq: int, messages: list[dict]) -> None:
        async with self.conn() as c:
            async with c.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO messages (session_id, seq, role, content) VALUES (%s, %s, %s, %s)",
                    [
                        (session_id, start_seq + i, m["role"], Jsonb(m["content"]))
                        for i, m in enumerate(messages)
                    ],
                )
            await c.execute("UPDATE sessions SET updated_at = now() WHERE id = %s", (session_id,))

    # ---- memory -------------------------------------------------------------------------------
    async def memories(self, customer_id: str, limit: int = 8) -> list[str]:
        async with self.conn() as c:
            cur = await c.execute(
                "SELECT fact FROM memories WHERE customer_id = %s ORDER BY updated_at DESC LIMIT %s",
                (customer_id, limit),
            )
            return [r["fact"] for r in await cur.fetchall()]

    async def add_memories(self, customer_id: str, session_id: UUID, facts: list[tuple[str, str]]) -> None:
        async with self.conn() as c, c.cursor() as cur:
            await cur.executemany(
                "INSERT INTO memories (customer_id, fact, category, source_session) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (customer_id, fact) DO UPDATE SET updated_at = now()",
                [(customer_id, fact, category, session_id) for fact, category in facts],
            )
