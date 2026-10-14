"""Load demo customers and orders into the database in RELAY_DATABASE_URL."""

import asyncio
from datetime import UTC, datetime

from app.config import settings
from app.db import Store, open_pool
from app.seed import seed

DEMO = {
    "customers": [{"id": "c_77", "name": "Ada Lovelace"}, {"id": "c_91", "name": "Grace Hopper"}],
    "orders": [
        {"id": 1042, "customer_id": "c_77", "status": "delivered", "total": 45.0, "days_ago": 6},
        {"id": 3001, "customer_id": "c_77", "status": "delivered", "total": 640.0, "days_ago": 10},
        {"id": 7001, "customer_id": "c_77", "status": "shipped", "total": 89.0, "eta_in_days": 3},
        {"id": 2210, "customer_id": "c_91", "status": "delivered", "total": 120.0, "days_ago": 3},
    ],
}


async def main() -> None:
    pool = await open_pool(settings.database_url)
    store = Store(pool)
    await store.apply_schema()
    await seed(store, DEMO, datetime.now(UTC))
    await pool.close()
    print(
        "Seeded customers c_77 and c_91. Try: order 1042 (refundable), 3001 (needs approval), 7001 (shipped)."
    )


if __name__ == "__main__":
    asyncio.run(main())
