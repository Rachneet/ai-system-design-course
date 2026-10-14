# ruff: noqa: ASYNC220, ASYNC221 - a load-test harness that starts local servers
"""Measure the latency Switchboard adds: the same requests sent directly to a mock provider and through the
gateway, both running as real servers on localhost.

    uv run python -m loadtest.overhead --requests 2000 --concurrency 32

Starts a throwaway Postgres (pgserver), migrates it, runs the mock provider and the gateway with uvicorn, provisions
a key through the admin API, then reports p50/p95/p99 for both paths and the difference.
"""

import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
import time

import httpx
import pgserver

BODY = {"model": "claude-sonnet-5-5", "max_tokens": 64, "messages": [{"role": "user", "content": "ping " * 50}]}
ADMIN = "loadtest-admin-token-0123456789"


def pct(values: list[float], p: float) -> float:
    return sorted(values)[min(len(values) - 1, int(p / 100 * len(values)))] * 1000


GATEWAY_MS: list[float] = []


async def fire(url: str, headers: dict, n: int, concurrency: int) -> list[float]:
    sem, out = asyncio.Semaphore(concurrency), []
    async with httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=concurrency)) as client:

        async def one():
            async with sem:
                t = time.perf_counter()
                r = await client.post(url, json=BODY, headers=headers)
                r.raise_for_status()
                out.append(time.perf_counter() - t)
                if "server-timing" in r.headers:
                    GATEWAY_MS.append(float(r.headers["server-timing"].split("gateway;dur=")[1].split(",")[0]) / 1000)

        await asyncio.gather(*(one() for _ in range(n)))
    return out


async def wait_up(url: str) -> None:
    for _ in range(100):
        try:
            async with httpx.AsyncClient() as c:
                if (await c.get(url)).status_code < 500:
                    return
        except httpx.TransportError:
            pass
        await asyncio.sleep(0.1)
    raise RuntimeError(f"{url} did not start")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=int, default=2000)
    ap.add_argument("--concurrency", type=int, default=32)
    args = ap.parse_args()

    srv = pgserver.get_server(tempfile.mkdtemp(), cleanup_mode="stop")
    env = os.environ | {
        "SWITCHBOARD_DATABASE_URL": srv.get_uri(),
        "SWITCHBOARD_ADMIN_TOKEN": ADMIN,
        "SWITCHBOARD_ANTHROPIC_API_KEY": "mock",
        "SWITCHBOARD_ANTHROPIC_BASE_URL": "http://127.0.0.1:18001",
    }
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
    procs = [
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "tests.mock_upstream:app",
                "--port",
                "18001",
                "--log-level",
                "warning",
                "--no-access-log",
            ],
            env=env,
        ),
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "switchboard.main:app",
                "--port",
                "18000",
                "--log-level",
                "warning",
                "--no-access-log",
            ],
            env=env,
            stdout=subprocess.DEVNULL,
        ),
    ]
    try:
        await wait_up("http://127.0.0.1:18001/docs")
        await wait_up("http://127.0.0.1:18000/healthz")
        admin = {"Authorization": f"Bearer {ADMIN}"}
        async with httpx.AsyncClient(base_url="http://127.0.0.1:18000", headers=admin) as c:
            await c.post("/admin/orgs", json={"id": "load", "name": "Load"})
            await c.post("/admin/teams", json={"id": "load", "org_id": "load", "name": "Load"})
            await c.post(
                "/admin/apps",
                json={
                    "id": "load",
                    "team_id": "load",
                    "name": "Load",
                    "rpm": 100000,
                    "tpm": 100000000,
                    "pii_mode": "detect",
                },
            )
            key = (await c.post("/admin/apps/load/keys", json={})).json()["key"]
        warm = min(200, args.requests)
        await fire("http://127.0.0.1:18001/v1/messages", {}, warm, args.concurrency)
        await fire("http://127.0.0.1:18000/v1/messages", {"x-api-key": key}, warm, args.concurrency)
        GATEWAY_MS.clear()
        gateway = await fire("http://127.0.0.1:18000/v1/messages", {"x-api-key": key}, args.requests, args.concurrency)
        print(f"{args.requests} requests, concurrency {args.concurrency}, PII detection on, one gateway process")
        print(f"{'measure':34} {'p50 ms':>8} {'p95 ms':>8} {'p99 ms':>8}")
        rows = (("end to end through the gateway", gateway), ("gateway's own time (Server-Timing)", GATEWAY_MS))
        for name, xs in rows:
            print(f"{name:34} {pct(xs, 50):8.1f} {pct(xs, 95):8.1f} {pct(xs, 99):8.1f}")
        print(f"throughput: {args.requests / sum(gateway) * args.concurrency:.0f} requests/s (approx.)")
    finally:
        for p in procs:
            p.terminate()
            p.wait(timeout=10)
        srv.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
