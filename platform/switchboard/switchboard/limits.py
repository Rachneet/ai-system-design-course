"""Per-app rate limits, enforced locally on each instance (see ADR 0002).

A shared Postgres bucket is exact but every request updates the same row, and under load those row locks were
the gateway's main cost. Instead each instance keeps in-memory token buckets sized at limit / live_instances.
Instances heartbeat into Postgres every few seconds, so a scale-out or a crash rebalances within one interval.
Budgets, which protect money, stay globally enforced from the ledger.
"""

import asyncio
import contextlib
import time
import uuid

from psycopg_pool import AsyncConnectionPool


class LocalBucket:
    def __init__(self, per_minute: float, clock=time.monotonic):
        self.capacity = per_minute  # burst equals one minute of capacity
        self.tokens = per_minute
        self.rate = per_minute / 60.0
        self.updated = clock()
        self.clock = clock

    def resize(self, per_minute: float) -> None:
        if per_minute != self.capacity:
            self.tokens = min(self.tokens, per_minute)
            self.capacity, self.rate = per_minute, per_minute / 60.0

    def take(self, cost: float) -> float:
        now = self.clock()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if cost > self.capacity:
            return 60.0  # a single request larger than the whole per-minute budget never fits
        if self.tokens >= cost:
            self.tokens -= cost
            return 0.0
        return max(0.001, (cost - self.tokens) / self.rate)

    def refund(self, amount: float) -> None:
        if amount > 0:
            self.tokens = min(self.capacity, self.tokens + amount)


class Limiter:
    def __init__(self, pool: AsyncConnectionPool | None = None, heartbeat_s: float = 5.0, clock=time.monotonic):
        self.pool, self.heartbeat_s, self.clock = pool, heartbeat_s, clock
        self.instance_id = uuid.uuid4().hex[:12]
        self.instances = 1
        self.buckets: dict[str, LocalBucket] = {}
        self._task: asyncio.Task | None = None

    def bucket(self, key: str, per_minute: int) -> LocalBucket:
        share = max(1.0, per_minute / self.instances)
        b = self.buckets.get(key)
        if b is None:
            b = self.buckets[key] = LocalBucket(share, self.clock)
        else:
            b.resize(share)
        return b

    def take(self, key: str, per_minute: int, cost: float = 1.0) -> float:
        """0 if allowed, else seconds until this instance's share has room. No I/O on the request path."""
        return self.bucket(key, per_minute).take(cost)

    def refund(self, key: str, per_minute: int, amount: float) -> None:
        self.bucket(key, per_minute).refund(amount)

    async def beat(self) -> None:
        async with self.pool.connection() as c:
            await c.execute(
                "INSERT INTO instances (id, last_seen) VALUES (%s, now()) "
                "ON CONFLICT (id) DO UPDATE SET last_seen = now()",
                (self.instance_id,),
            )
            row = await (
                await c.execute(
                    "SELECT count(*) AS n FROM instances WHERE last_seen > now() - make_interval(secs => %s)",
                    (self.heartbeat_s * 3,),
                )
            ).fetchone()
            await c.execute("DELETE FROM instances WHERE last_seen < now() - interval '1 hour'")
        self.instances = max(1, row["n"])

    async def start(self) -> None:
        await self.beat()

        async def loop():
            while True:
                await asyncio.sleep(self.heartbeat_s)
                with contextlib.suppress(Exception):  # a missed beat keeps the last known count
                    await self.beat()

        self._task = asyncio.create_task(loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        with contextlib.suppress(Exception):
            async with self.pool.connection() as c:
                await c.execute("DELETE FROM instances WHERE id = %s", (self.instance_id,))
