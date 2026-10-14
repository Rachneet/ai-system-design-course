import asyncio

from app.embeddings import HashEmbedder
from evals import run
from tests.fakes import FakeQuarantine, ScriptedLLM, text, tool_use


async def test_one_trial_end_to_end(pg_url, monkeypatch):
    """The whole harness except the model: shared KB schema, per-trial schema, seeding, guard, grading."""
    monkeypatch.setattr(run.settings, "database_url", pg_url)
    await run.build_kb(HashEmbedder())
    case = next(c for c in run.load_cases("all") if c["id"] == "refund-under-limit-004")
    llm = ScriptedLLM(
        tool_use(("get_order", {"order_id": 1042})),
        tool_use(("issue_refund", {"order_id": 1042, "amount": 45.0, "reason": "torn rain fly"})),
        text("Done: I've refunded $45.00 for order 1042."),
    )
    deps = run.Deps(llm=llm, models=(HashEmbedder(), None), quarantine=FakeQuarantine())
    result = await run.run_one(case, 0, deps, asyncio.Semaphore(1))
    assert result["pass"], result["fails"]
    assert result["steps"] == 3 and result["guard_failures"] == []
