"""Online evaluation: judge a sample of live sessions, plus every thumbs-down, and keep failures for review."""

from uuid import UUID

from . import metrics
from .db import Store
from .judges import CRITERIA, render


async def judge_session(store: Store, judge, payload: dict) -> list[dict]:
    session_id = UUID(payload["session_id"])
    transcript = render(await store.load_session(session_id, payload["customer_id"]))
    out = []
    for name in CRITERIA:
        v = await judge.judge(name, transcript)
        metrics.online_verdicts.labels(judge=name, verdict=v.verdict).inc()
        async with store.conn() as c:
            await c.execute(
                "INSERT INTO online_judgements (session_id, judge, verdict, reasoning, trigger) "
                "VALUES (%s, %s, %s, %s, %s)",
                (session_id, name, v.verdict, v.reasoning[:2000], payload.get("trigger", "sample")),
            )
        out.append({"judge": name, "verdict": v.verdict})
    return out


async def review_queue(store: Store, limit: int = 50) -> list[dict]:
    """What a human should read next: judge failures and thumbs-down, newest first."""
    async with store.conn() as c:
        return await (
            await c.execute(
                "SELECT 'judge' AS source, session_id, judge AS detail, reasoning AS note, created_at "
                "FROM online_judgements WHERE verdict = 'fail' AND NOT reviewed "
                "UNION ALL SELECT 'feedback', session_id, coalesce(reason, 'thumbs down'), comment, created_at "
                "FROM feedback WHERE rating = 'down' ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
        ).fetchall()
