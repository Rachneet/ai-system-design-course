"""Error analysis: read traces, note the first failure in each, group the notes, and count them.

uv run python -m evals.error_analysis worksheet runs/main.json --n 60    # writes analysis/worksheet.md
# ... open the worksheet, read each transcript, fill in "first failure" and "category" ...
uv run python -m evals.error_analysis tally analysis/worksheet.md
uv run python -m evals.error_analysis to-case runs/main.json refund-under-limit-004 2   # trace -> case skeleton
"""

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

import yaml

from app.judges import render

from .run import load_cases

HERE = Path(__file__).parent


def worksheet(run_path: str, n: int, seed: int = 0) -> str:
    results = [r for r in json.loads(Path(run_path).read_text())["results"] if r.get("transcript")]
    rng = random.Random(seed)
    failed = [r for r in results if not r["pass"]]
    passed = [r for r in results if r["pass"]]
    # Up to half failures, the rest random passes; top up from whichever side has more if one runs short.
    picked = failed[: n // 2] + rng.sample(passed, k=min(len(passed), n - min(len(failed), n // 2)))
    picked += failed[n // 2 :][: n - len(picked)]
    out = [
        "# Error analysis worksheet",
        "",
        "For each conversation, write the FIRST thing that went wrong (or `ok`), then a short category. Name",
        'categories after what you see ("refund before eligibility check"), not generic qualities ("helpfulness").',
        "",
    ]
    for r in picked:
        out += [
            f"## {r['id']} (trial {r['trial']}, automated: {'pass' if r['pass'] else 'fail'})",
            "",
            "```text",
            render(r["transcript"]),
            "```",
            "",
            f"Automated failures: {'; '.join(r['fails']) or 'none'}",
            "",
            "- first failure: ",
            "- category: ",
            "",
        ]
    return "\n".join(out)


def tally(path: str) -> list[tuple[str, int]]:
    cats = re.findall(r"^- category:[ \t]*(.+?)[ \t]*$", Path(path).read_text(), re.MULTILINE)
    counts = Counter(c.strip().lower() for c in cats if c.strip() and c.strip().lower() != "ok")
    return counts.most_common()


def to_case(run_path: str, case_id: str, trial: int) -> str:
    """A regression-case skeleton from a real trace: same environment and messages, expectations left for you."""
    result = next(
        r
        for r in json.loads(Path(run_path).read_text())["results"]
        if r["id"] == case_id and r["trial"] == trial
    )
    original = next(c for c in load_cases("all") if c["id"] == case_id)
    user_turns = [
        b["text"]
        for m in result["transcript"]
        if m["role"] == "user" and isinstance(m["content"], list)
        for b in m["content"]
        if b.get("type") == "text" and not b["text"].startswith("<guardrail>")
    ]
    case = {
        "id": f"{case_id}-regression-{trial}",
        "category": original["category"],
        "source": "prod-trace",
        "env": original["env"],
        **({"turns": user_turns} if len(user_turns) > 1 else {"input": user_turns[0]}),
        "expect": {"must_not_call": [], "end_state": {}, "max_steps": 6},
    }
    note = f"# From {run_path}, {case_id} trial {trial}. Failures: {'; '.join(result['fails'])}\n# TODO: fill in expect.\n"
    return note + yaml.safe_dump([case], sort_keys=False, width=120)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("worksheet")
    w.add_argument("run")
    w.add_argument("--n", type=int, default=60)
    w.add_argument("--out", default=str(HERE / "analysis" / "worksheet.md"))
    t = sub.add_parser("tally")
    t.add_argument("worksheet")
    c = sub.add_parser("to-case")
    c.add_argument("run")
    c.add_argument("case_id")
    c.add_argument("trial", type=int)
    args = ap.parse_args()
    if args.cmd == "worksheet":
        Path(args.out).write_text(worksheet(args.run, args.n))
        print(f"wrote {args.out}")
    elif args.cmd == "tally":
        rows = tally(args.worksheet)
        print("| Category | Count |\n|---|---|\n" + "\n".join(f"| {k} | {v} |" for k, v in rows))
    else:
        print(to_case(args.run, args.case_id, args.trial))


if __name__ == "__main__":
    main()
