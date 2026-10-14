"""Apply the schema once, as a release step before new code takes traffic: uv run python -m app.migrate

The schema uses only additive, idempotent statements (CREATE ... IF NOT EXISTS, ADD COLUMN IF NOT EXISTS), so the
previous release keeps working against it and rollbacks need no down-migration (expand, then contract later).
"""

import asyncio

from .config import settings
from .db import Store, open_pool


async def main() -> None:
    pool = await open_pool(settings.database_url, max_size=1)
    await Store(pool).apply_schema()
    await pool.close()
    print("schema applied")


if __name__ == "__main__":
    asyncio.run(main())
