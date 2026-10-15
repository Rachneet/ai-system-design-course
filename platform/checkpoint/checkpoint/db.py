from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


async def open_pool(url: str, schema: str | None = None, max_size: int = 20) -> AsyncConnectionPool:
    kwargs: dict = {"row_factory": dict_row, "autocommit": True}
    if schema:
        kwargs["options"] = f"-c search_path={schema},public"
    pool = AsyncConnectionPool(url, min_size=2, max_size=max_size, open=False, kwargs=kwargs)
    await pool.open(wait=True)
    return pool
