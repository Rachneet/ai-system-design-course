"""Seed data from a plain dict, with dates relative to a fixed 'now' so tests and evals are reproducible."""

from datetime import datetime, timedelta

from psycopg.types.json import Jsonb

from .db import Store


async def seed(store: Store, data: dict, now: datetime) -> None:
    async with store.conn() as c:
        for cust in data.get("customers", []):
            await c.execute(
                "INSERT INTO customers (id, name, email) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (cust["id"], cust.get("name", cust["id"]), cust.get("email", f"{cust['id']}@example.com")),
            )
        for o in data.get("orders", []):
            await c.execute(
                "INSERT INTO customers (id, name, email) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (o["customer_id"], o["customer_id"], f"{o['customer_id']}@example.com"),
            )
            delivered = now - timedelta(days=o["days_ago"]) if o.get("status") == "delivered" else None
            eta = (now + timedelta(days=o["eta_in_days"])).date() if "eta_in_days" in o else None
            items = o.get("items") or [
                {
                    "sku": "TENT-RDG-2P",
                    "name": "Ridgeline 2P tent",
                    "category": "tent",
                    "qty": 1,
                    "price": o["total"],
                }
            ]
            tracking = f"NW{o['id']}" if o.get("status") in ("shipped", "delivered") else None
            await c.execute(
                "INSERT INTO orders (id, customer_id, status, total, items, eta, delivered_at, tracking_number) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (o["id"], o["customer_id"], o["status"], o["total"], Jsonb(items), eta, delivered, tracking),
            )
        for rv in data.get("reviews", []):
            await c.execute(
                "INSERT INTO reviews (sku, rating, body) VALUES (%s, %s, %s)",
                (rv["sku"], rv["rating"], rv["body"]),
            )
        for r in data.get("refunds", []):
            await c.execute(
                "INSERT INTO refunds (order_id, amount, reason) VALUES (%s, %s, %s)",
                (r["order_id"], r["amount"], "seed"),
            )
