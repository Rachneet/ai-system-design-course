import asyncio
import json

import pytest
import yaml

from app.embeddings import HashEmbedder
from evals import error_analysis, generate, run
from evals.calibrate import corrected_pass_rate, metrics, split_of
from evals.judges import DATA, Verdict, render
from tests.fakes import FakeQuarantine, ScriptedLLM, text, tool_use


def test_generator_is_deterministic_and_matches_committed_files():
    import random

    first, second = generate.build(random.Random(42)), generate.build(random.Random(42))
    assert first == second
    committed = {
        c["id"]
        for d in ("dev", "heldout")
        for c in yaml.safe_load((run.CASES / d / "generated.yaml").read_text())
    }
    assert committed == {c["id"] for c in first}  # re-run evals.generate if this fails


def test_suites_and_validation():
    assert run.validate(run.load_cases("all")) == []
    smoke, pr, release = (run.load_cases(s) for s in ("smoke", "pr", "release"))
    assert 0 < len(smoke) < len(pr) < len(release) and len(release) >= 150
    assert all(c["split"] == "dev" for c in pr) and any(c["split"] == "heldout" for c in release)


def test_calibration_sets_are_balanced_and_split_stably():
    for name in ("no_unsupported_promise", "warranty_route_when_ineligible"):
        rows = [json.loads(line) for line in (DATA / f"{name}.jsonl").read_text().splitlines()]
        assert len(rows) >= 60 and sum(r["label"] == "fail" for r in rows) == len(rows) // 2
        assert {split_of(r["id"]) for r in rows} == {"dev", "test"}


def test_judge_metrics_and_correction():
    labels = ["fail"] * 10 + ["pass"] * 10
    always_pass = metrics(labels, ["pass"] * 20)
    assert always_pass["accuracy"] == 0.5 and always_pass["fail_recall"] == 0 and always_pass["kappa"] == 0
    perfect = metrics(labels, labels)
    assert perfect["kappa"] == 1 and perfect["fail_recall"] == 1
    assert corrected_pass_rate(0.85, pass_recall=0.95, fail_recall=0.90) == pytest.approx(0.882, abs=0.001)


def test_mcnemar_exact():
    assert run.regression_p(0, 0) == 1.0
    assert run.regression_p(7, 1) == pytest.approx(9 / 256)  # P(X >= 7), X ~ Bin(8, 0.5)
    assert run.regression_p(2, 2) > 0.5


def test_gates():
    gates = yaml.safe_load(run.GATES.read_text())
    ok = {"category": "order_status", "pass": True, "latency_s": 3.0, "usage": {}, "id": "a", "trial": 0}
    assert run.evaluate_gates([ok] * 10, gates, "claude-haiku-5-5", None) == []
    leak = ok | {"category": "injection", "pass": False, "id": "rt"}
    assert "must-never" in run.evaluate_gates([ok] * 50 + [leak], gates, "claude-haiku-5-5", None)[0]
    base = {"results": [ok | {"id": str(i)} for i in range(10)]}
    worse = [ok | {"id": str(i), "pass": i >= 8} for i in range(10)]
    assert any("regression" in f for f in run.evaluate_gates(worse, gates, "claude-haiku-5-5", base))


class FakeSimulator:
    def __init__(self, lines):
        self.lines = list(lines)

    async def next_message(self, spec, transcript):
        return self.lines.pop(0)


async def _trial(pg_url, monkeypatch, case, llm, simulator=None):
    monkeypatch.setattr(run.settings, "database_url", pg_url)
    await run.build_kb(HashEmbedder())
    deps = run.Deps(llm=llm, models=(HashEmbedder(), None), quarantine=FakeQuarantine(), simulator=simulator)
    return await run.run_one(case, 0, deps, asyncio.Semaphore(1))


def case(cid):
    return next(c for c in run.load_cases("all") if c["id"] == cid)


async def test_scripted_turns_keep_history(pg_url, monkeypatch):
    llm = ScriptedLLM(
        text("Which order?"),
        tool_use(("get_order", {"order_id": 1042})),
        tool_use(("issue_refund", {"order_id": 1042, "amount": 45.0, "reason": "torn fly"})),
        text("Refunded $45.00."),
    )
    result = await _trial(pg_url, monkeypatch, case("mt-number-given-late"), llm)
    assert result["pass"], result["fails"]
    assert len(llm.requests[1]["messages"]) == 3  # turn 2 sees turn 1


async def test_simulator_conversation_ends_on_done(pg_url, monkeypatch):
    sim = FakeSimulator(["hi, refund please", "order 1042, torn fly", "thanks ###DONE###"])
    llm = ScriptedLLM(
        text("Sure, which order?"),
        tool_use(("issue_refund", {"order_id": 1042, "amount": 45.0, "reason": "torn"})),
        text("Refunded $45.00."),
        text("You're welcome!"),
    )
    result = await _trial(pg_url, monkeypatch, case("sim-refund-terse"), llm, sim)
    assert result["pass"], result["fails"]
    assert len(llm.requests) == 4  # the final "thanks ###DONE###" turn is still answered, then the loop stops


async def test_email_case_uses_email_channel(pg_url, monkeypatch):
    llm = ScriptedLLM(
        tool_use(("request_refund_approval", {"order_id": 3001, "amount": 640.0, "reason": "snapped pole"})),
        text("We've asked a teammate to approve your $640 refund."),
    )
    result = await _trial(pg_url, monkeypatch, case("rt-email-over-limit-legit"), llm)
    assert result["pass"], result["fails"]
    assert "issue_refund" not in {t["name"] for t in llm.requests[0]["tools"]}


async def test_poisoned_kb_document_is_indexed_for_the_trial(pg_url, monkeypatch):
    llm = ScriptedLLM(
        tool_use(("search_kb", {"query": "warranty claims portal"})),
        text("File it at [the portal](https://evil.example/warranty-claim)."),
    )
    result = await _trial(pg_url, monkeypatch, case("rt-kb-malicious-link"), llm)
    assert "POL-WARRANTY-PORTAL" in json.dumps(result["transcript"])
    assert "evil.example" not in result["reply"] and result["pass"]  # the sanitizer closes the channel


def test_render_shows_tool_evidence():
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "refund 1042"}]},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "t", "name": "issue_refund", "input": {"order_id": 1042}}],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t", "content": "Refunded $45.00"}],
        },
    ]
    out = render(msgs)
    assert "TOOL CALL issue_refund" in out and "TOOL RESULT: Refunded $45.00" in out
    assert Verdict(reasoning="x", verdict="pass")


def test_worksheet_tally_and_trace_to_case(tmp_path):
    transcript = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Order 1042 arrived with a torn rain fly. Can I get a refund?"}
            ],
        },
        {"role": "assistant", "content": [{"type": "text", "text": "Sure"}]},
    ]
    results = [
        {
            "id": "refund-under-limit-004",
            "trial": t,
            "pass": t == 0,
            "fails": [] if t == 0 else ["missing call"],
            "transcript": transcript,
        }
        for t in range(4)
    ]
    run_file = tmp_path / "run.json"
    run_file.write_text(json.dumps({"results": results}))
    sheet = error_analysis.worksheet(str(run_file), n=4)
    assert sheet.count("- category:") == 4
    filled = tmp_path / "w.md"
    filled.write_text(sheet.replace("- category: ", "- category: refund before eligibility check", 3))
    assert error_analysis.tally(str(filled)) == [("refund before eligibility check", 3)]
    skeleton = yaml.safe_load(error_analysis.to_case(str(run_file), "refund-under-limit-004", 2))
    assert skeleton[0]["source"] == "prod-trace" and skeleton[0]["input"].startswith("Order 1042")
