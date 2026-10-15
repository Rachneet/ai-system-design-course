"""Postgres access. Every tenant-owned table has row-level security keyed on the helpdesk.tenant setting, and the app
connects as a role without BYPASSRLS, so a query that forgets its tenant filter returns nothing rather than another
tenant's rows. tenant() sets the tenant for one transaction only (set_config(..., true)), so a pooled connection
never carries one request's tenant into the next."""

from contextlib import asynccontextmanager

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


async def open_pool(url: str, schema: str | None = None, max_size: int = 20) -> AsyncConnectionPool:
    kwargs: dict = {"row_factory": dict_row, "autocommit": True}
    if schema:
        kwargs["options"] = f"-c search_path={schema},public"
    pool = AsyncConnectionPool(url, min_size=2, max_size=max_size, open=False, kwargs=kwargs)
    await pool.open(wait=True)
    return pool


@asynccontextmanager
async def tenant(pool: AsyncConnectionPool, name: str):
    """A connection in a transaction scoped to one tenant."""
    async with pool.connection() as c, c.transaction():
        await c.execute("SELECT set_config('helpdesk.tenant', %s, true)", (name,))
        yield c
