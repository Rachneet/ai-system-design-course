"""foundry issue "Fix the rounding bug in invoice totals"   one issue, end to end
foundry batch issues.json                              each issue in a JSON list of strings
foundry eval evals/tasks --trials 3                    the coder alone, on tasks with a hidden check

Model calls go to SWITCHBOARD_URL with FOUNDRY_SWITCHBOARD_KEY. Every job is appended to the ledger."""

import argparse
import json
import shutil
import sys
import tempfile
import tomllib
from dataclasses import asdict
from pathlib import Path

from .config import load
from .factory import handle
from .harness import Harness
from .model import Model
from .sandbox import Workspace, git


def evaluate(tasks: Path, trials: int, model: Model) -> dict:
    """Each task is a directory with task.toml (issue, check) and repo/ (the code as it was before the fix)."""
    report = []
    for task in sorted(p for p in tasks.iterdir() if (p / "task.toml").exists()):
        spec = tomllib.loads((task / "task.toml").read_text())
        passes, tokens = 0, 0
        for trial in range(trials):
            source = Path(tempfile.mkdtemp(prefix="foundry-task-")) / "repo"
            shutil.copytree(task / "repo", source)
            git(source, "init", "--quiet")
            git(source, "add", "--all")
            git(source, "-c", "user.name=eval", "-c", "user.email=eval@localhost", "commit", "--quiet", "-m", "task")
            cfg = load(source)
            ws = Workspace.clone(source, cfg.sandbox_prefix, cfg.timeout_s)
            out = Harness(ws, cfg, model, source, f"eval:{task.name}:{trial}:coder").run(spec["issue"])
            (ws.root / spec.get("hidden_test_path", "_hidden_test.py")).write_text(spec.get("hidden_test", ""))
            passes += out.status == "finished" and ws.run(spec["check"]).code == 0
            tokens += out.tokens
            ws.remove()
            shutil.rmtree(source.parent, ignore_errors=True)
        report.append({"task": task.name, "passed": passes, "trials": trials, "tokens": tokens})
    n = len(report) or 1
    return {
        "pass_at_1": round(sum(r["passed"] / r["trials"] for r in report) / n, 3),
        "pass_hat_k": round(sum(r["passed"] == r["trials"] for r in report) / n, 3),
        "tasks": report,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="foundry", description=__doc__.split("\n\n")[0])
    p.add_argument("--repo", type=Path, default=Path("."))
    p.add_argument("--ledger", type=Path, default=Path.home() / ".foundry" / "ledger.jsonl")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("issue").add_argument("text")
    sub.add_parser("batch").add_argument("file", type=Path)
    ev = sub.add_parser("eval")
    ev.add_argument("tasks", type=Path)
    ev.add_argument("--trials", type=int, default=3)
    args = p.parse_args(argv)

    cfg = load(args.repo)
    model = Model(cfg.switchboard_url, cfg.switchboard_key)
    if args.cmd == "eval":
        print(json.dumps(evaluate(args.tasks, args.trials, model), indent=2))
        return 0
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    issues = [args.text] if args.cmd == "issue" else json.loads(args.file.read_text())
    failed = 0
    for issue in issues:
        result = handle(args.repo, issue, cfg, model, args.ledger)
        failed += result.status not in ("ready", "merged")
        print(
            json.dumps(
                {k: v for k, v in asdict(result).items() if k != "gates"}
                | {"gates": {g.name: g.passed for g in result.gates}}
            )
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
