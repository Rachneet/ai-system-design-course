"""Measure each judge against labelled examples before trusting its scores.

uv run python -m evals.calibrate                        # both judges, on the test half
uv run python -m evals.calibrate --split dev            # iterate on the judge prompt with the dev half only
"""

import argparse
import asyncio
import hashlib
import json

from app.config import settings
from app.judges import CRITERIA, AnthropicJudge

from .paths import JUDGE_DATA as DATA


def split_of(example_id: str) -> str:
    """Stable 50/50 split by id, so the test half never leaks into prompt tuning."""
    return "dev" if int(hashlib.sha256(example_id.encode()).hexdigest(), 16) % 2 == 0 else "test"


def metrics(labels: list[str], predictions: list[str]) -> dict:
    """'fail' is the positive class: catching failures is the judge's job."""
    tp = sum(y == "fail" and p == "fail" for y, p in zip(labels, predictions, strict=True))
    tn = sum(y == "pass" and p == "pass" for y, p in zip(labels, predictions, strict=True))
    fp = sum(y == "pass" and p == "fail" for y, p in zip(labels, predictions, strict=True))
    fn = sum(y == "fail" and p == "pass" for y, p in zip(labels, predictions, strict=True))
    n = tp + tn + fp + fn
    observed = (tp + tn) / n
    expected = ((tp + fp) * (tp + fn) + (tn + fn) * (tn + fp)) / (n * n)
    kappa = (observed - expected) / (1 - expected) if expected < 1 else 1.0
    return {
        "n": n,
        "fail_recall": tp / (tp + fn) if tp + fn else None,
        "pass_recall": tn / (tn + fp) if tn + fp else None,
        "accuracy": observed,
        "kappa": kappa,
    }


def corrected_pass_rate(judged_pass_rate: float, pass_recall: float, fail_recall: float) -> float:
    """Estimate the true pass rate from a judge's measured error rates (clipped to [0, 1])."""
    denom = pass_recall + fail_recall - 1
    if denom <= 0:
        raise ValueError("judge is no better than chance; its scores cannot be corrected")
    return min(1.0, max(0.0, (judged_pass_rate + fail_recall - 1) / denom))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], default="test")
    ap.add_argument("--judge", choices=sorted(CRITERIA))
    args = ap.parse_args()
    judge = AnthropicJudge(settings.judge_model)
    for name in [args.judge] if args.judge else sorted(CRITERIA):
        rows = [json.loads(line) for line in (DATA / f"{name}.jsonl").read_text().splitlines()]
        rows = [r for r in rows if split_of(r["id"]) == args.split]
        verdicts = await asyncio.gather(*(judge.judge(name, r["transcript"]) for r in rows))
        m = metrics([r["label"] for r in rows], [v.verdict for v in verdicts])
        print(
            f"{name} ({args.split}, {settings.judge_model}): n={m['n']} fail recall={m['fail_recall']:.2f} "
            f"pass recall={m['pass_recall']:.2f} kappa={m['kappa']:.2f}"
        )
        for r, v in zip(rows, verdicts, strict=True):
            if v.verdict != r["label"]:
                print(f"  disagree {r['id']} label={r['label']} ({r['note']}): {v.reasoning[:140]}")


if __name__ == "__main__":
    asyncio.run(main())
