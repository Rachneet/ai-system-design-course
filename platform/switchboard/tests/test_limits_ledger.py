from decimal import Decimal

from switchboard.keys import Caller
from switchboard.ledger import LedgerWriter
from switchboard.limits import Limiter, LocalBucket

CALLER = Caller("k1", "a1", "t1", "o1", (), 60, 1000, "off", False, 30)


def test_bucket_refills_and_rejects_oversized():
    now = [0.0]
    b = LocalBucket(60, clock=lambda: now[0])
    assert all(b.take(1) == 0 for _ in range(60)) and b.take(1) > 0
    now[0] = 1.0
    assert b.take(1) == 0  # one per second refilled
    assert b.take(500) == 60.0


def test_limits_are_split_across_live_instances():
    lim = Limiter()
    lim.instances = 4
    allowed = sum(lim.take("rpm:a", 100) == 0 for _ in range(100))
    assert allowed == 25


async def test_ledger_batches_and_never_double_counts(gw):
    pool = gw.app.state.pool
    async with pool.connection() as c:
        await c.execute(
            "INSERT INTO orgs VALUES ('o1', 'O'); INSERT INTO teams VALUES ('t1', 'o1', 'T'); "
            "INSERT INTO apps (id, team_id, name) VALUES ('a1', 't1', 'A'); "
            "INSERT INTO api_keys (id, app_id, secret_hash) VALUES ('k1', 'a1', 'x')"
        )
    writer = LedgerWriter(pool)
    for i in range(50):
        writer.add(
            CALLER,
            {
                "request_id": f"r{i}",
                "requested_model": "m",
                "served_model": "m",
                "status": 200,
                "stream": False,
                "latency_ms": 5,
                "usage": {},
            },
            Decimal("0.01"),
            None,
        )
    batch = list(writer.queue)
    assert await writer.flush() == 50
    writer.queue = batch  # simulate a retry of a batch that was already committed
    assert await writer.flush() == 0
    async with pool.connection() as c:
        rows = await (await c.execute("SELECT scope, cost_usd, requests FROM spend_monthly ORDER BY scope")).fetchall()
    assert [(r["scope"], r["requests"], r["cost_usd"]) for r in rows] == [
        ("app", 50, Decimal("0.5")),
        ("org", 50, Decimal("0.5")),
        ("team", 50, Decimal("0.5")),
    ]


async def test_failed_flush_is_retried(gw, monkeypatch):
    writer = LedgerWriter(gw.app.state.pool)
    writer.add(
        CALLER,
        {"request_id": "x", "requested_model": "m", "status": 200, "stream": False, "latency_ms": 1, "usage": {}},
        Decimal(0),
        None,
    )

    async def boom(batch):
        raise RuntimeError("db down")

    monkeypatch.setattr(writer, "_write", boom)
    assert await writer.flush() == 0 and len(writer.queue) == 1
