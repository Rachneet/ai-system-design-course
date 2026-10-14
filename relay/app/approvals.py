"""Refund approvals as a state machine. Each transition is a guarded UPDATE, so double clicks and concurrent
workers cannot execute a refund twice."""

import hashlib
import json

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from .db import Store


async def pending(store: Store) -> list[dict]:
    async with store.conn() as c:
        return await (
            await c.execute(
                "SELECT a.id, a.order_id, a.amount, a.reason, a.created_at, o.customer_id FROM approvals a "
                "JOIN orders o ON o.id = a.order_id WHERE a.status = 'pending' ORDER BY a.created_at"
            )
        ).fetchall()


async def decide(store: Store, approval_id: int, approve: bool, staff_id: str) -> dict:
    async with store.conn() as c, c.transaction():
        row = await (
            await c.execute(
                "UPDATE approvals SET status = %s, decided_by = %s, decided_at = now() "
                "WHERE id = %s AND status = 'pending' RETURNING id, order_id, amount, reason",
                ("approved" if approve else "rejected", staff_id, approval_id),
            )
        ).fetchone()
        if row is None:
            current = await (
                await c.execute("SELECT status FROM approvals WHERE id = %s", (approval_id,))
            ).fetchone()
            if current is None:
                raise HTTPException(404, "Approval not found")
            raise HTTPException(409, f"Approval is already {current['status']}")
        if not approve:
            return {"id": approval_id, "status": "rejected"}
        await c.execute(
            "INSERT INTO refunds (order_id, amount, reason) VALUES (%s, %s, %s) ON CONFLICT (order_id) DO NOTHING",
            (row["order_id"], row["amount"], f"approved #{approval_id}: {row['reason']}"),
        )
        await c.execute(
            "UPDATE approvals SET status = 'executed' WHERE id = %s AND status = 'approved'", (approval_id,)
        )
    return {
        "id": approval_id,
        "status": "executed",
        "order_id": row["order_id"],
        "amount": float(row["amount"]),
    }


async def idempotent(store: Store, customer_id: str, key: str | None, request: dict, run) -> tuple[int, dict]:
    """Replay the stored response for a repeated Idempotency-Key; reject reuse of a key with a different request."""
    if key is None:
        return 200, await run()
    digest = hashlib.sha256(json.dumps(request, sort_keys=True, default=str).encode()).hexdigest()
    async with store.conn() as c:
        inserted = await (
            await c.execute(
                "INSERT INTO idempotency_keys (key, customer_id, request_hash) VALUES (%s, %s, %s) "
                "ON CONFLICT DO NOTHING RETURNING key",
                (key, customer_id, digest),
            )
        ).fetchone()
        if inserted is None:
            row = await (
                await c.execute(
                    "SELECT request_hash, status_code, response FROM idempotency_keys WHERE customer_id = %s AND key = %s",
                    (customer_id, key),
                )
            ).fetchone()
            if row["request_hash"] != digest:
                raise HTTPException(422, "This Idempotency-Key was already used for a different request")
            if row["status_code"] is None:
                raise HTTPException(409, "The original request is still in progress")
            return row["status_code"], row["response"]
    try:
        status, body = 200, await run()
    except HTTPException as e:
        status, body = e.status_code, {"detail": e.detail}
    async with store.conn() as c:
        await c.execute(
            "UPDATE idempotency_keys SET status_code = %s, response = %s WHERE customer_id = %s AND key = %s",
            (status, Jsonb(body), customer_id, key),
        )
    return status, body
