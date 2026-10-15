"""The software factory: one issue in, one reviewed and tested branch out, with a record of how it was made.

    issue -> coder (the harness, in a throwaway clone) -> gates -> reviewer -> branch -> merge, or wait for a person

Gates are deterministic and run on the result, not on what the agent says it did: the tests pass, the diff is
small enough, no protected path changed, no test file was deleted and no test function went missing, and no
secret appears in an added line. The reviewer is a second model that sees only the issue and the diff, never the
coder's reasoning, so it judges the change rather than the story. A change that passes everything becomes a branch
with provenance trailers; it is merged only when auto_merge is on, and otherwise waits for a person.
"""

import hashlib
import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path

from . import __version__
from .harness import SYSTEM, Harness
from .model import Model, ModelError
from .sandbox import Workspace, git

SECRET = re.compile(
    r"AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(sk-ant-|sk-)[A-Za-z0-9_-]{20,}|\b(ghp|github_pat)_[A-Za-z0-9_]{20,}"
)
REVIEW = """You review a proposed change to a repository. You see the issue and the diff only.
Approve only if the diff resolves the issue, changes nothing unrelated, and does not weaken tests, checks or
security. Answer with JSON only: {"approve": true or false, "reasons": ["..."]}."""
BOT = {
    k: v
    for who in ("AUTHOR", "COMMITTER")
    for k, v in ((f"GIT_{who}_NAME", "Foundry"), (f"GIT_{who}_EMAIL", "foundry@localhost"))
}


@dataclass
class Gate:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Result:
    job: str
    status: str  # merged | ready | rejected | failed
    branch: str = ""
    commit: str = ""
    gates: list[Gate] = field(default_factory=list)
    review: dict = field(default_factory=dict)
    tokens: int = 0
    summary: str = ""
    transcript: list[dict] = field(default_factory=list)  # every model turn and tool call, results cut short


def gates(ws: Workspace, cfg) -> list[Gate]:
    changes = ws.changed()
    diff = ws.diff()
    added = [line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
    removed = [line for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")]
    size = len(added) + len(removed)
    tests = ws.run(cfg.test)
    touched = [p for _, p in changes if any(fnmatchcase(p, g) for g in cfg.protected)]
    lost = [p for s, p in changes if s == "D" and "test" in p]
    defs = sum(1 for line in removed if re.match(r"-\s*def test_", line)) - sum(
        1 for a in added if re.match(r"\s*def test_", a)
    )
    return [
        Gate("changed", bool(changes), f"{len(changes)} files"),
        Gate("tests", tests.code == 0, tests.output[-1500:]),
        Gate("size", size <= cfg.max_changed_lines, f"{size} lines changed, limit {cfg.max_changed_lines}"),
        Gate("protected", not touched, ", ".join(touched)),
        Gate(
            "tests_kept",
            not lost and defs <= 0,
            ", ".join(lost) or (f"{defs} test functions removed" if defs > 0 else ""),
        ),
        Gate("secrets", not any(SECRET.search(a) for a in added), ""),
    ]


def review(model: Model, cfg, issue: str, diff: str, tag: str) -> tuple[dict, int]:
    messages = [
        {"role": "system", "content": REVIEW},
        {"role": "user", "content": f"Issue:\n{issue}\n\nDiff:\n{diff[:30_000]}"},
    ]
    message, used = model.chat(cfg.reviewer_model, messages, tag)
    try:
        verdict = json.loads(re.search(r"\{.*\}", message.get("content") or "", re.DOTALL)[0])
        return {"approve": verdict.get("approve") is True, "reasons": list(verdict.get("reasons", []))}, used
    except (TypeError, ValueError):
        return {"approve": False, "reasons": ["the reviewer did not answer in the required format"]}, used


def handle(repo: Path, issue: str, cfg, model: Model, ledger: Path) -> Result:
    job = uuid.uuid4().hex[:12]
    started = time.time()
    result = Result(job, "failed")
    ws = Workspace.clone(repo, cfg.sandbox_prefix, cfg.timeout_s)
    try:
        coder = Harness(ws, cfg, model, repo, f"job:{job}:coder").run(issue)
        result.tokens, result.summary, result.transcript = coder.tokens, coder.summary, coder.transcript
        if coder.status != "finished":
            result.summary = f"the coder stopped: {coder.status}"
            return result
        result.gates = gates(ws, cfg)
        if not all(g.passed for g in result.gates):
            result.status = "rejected"
            return result
        result.review, used = review(model, cfg, issue, ws.diff(), f"job:{job}:reviewer")
        result.tokens += used
        if not result.review["approve"]:
            result.status = "rejected"
            return result
        result.branch = f"foundry/{job}"
        prompt = hashlib.sha256(f"{SYSTEM}\n{issue}".encode()).hexdigest()[:16]
        message = (
            f"{coder.summary.splitlines()[0][:72] if coder.summary else 'Foundry change'}\n\n{coder.summary}\n\n"
            f"Foundry-Job: {job}\nFoundry-Coder: {cfg.coder_model}\nFoundry-Reviewer: {cfg.reviewer_model}\n"
            f"Foundry-Prompt: sha256:{prompt}\nFoundry-Gates: {','.join(g.name for g in result.gates)}"
        )
        git(ws.root, "commit", "--quiet", "-m", message, env=BOT)
        result.commit = git(ws.root, "rev-parse", "HEAD").strip()
        git(ws.root, "push", "--quiet", "origin", f"HEAD:refs/heads/{result.branch}")
        result.status = "ready"
        if cfg.auto_merge and not git(repo, "status", "--porcelain"):
            git(repo, "merge", "--quiet", "--ff-only", result.branch)
            result.status = "merged"
        return result
    except ModelError as e:
        result.summary = str(e)
        return result
    finally:
        ws.remove()
        record = asdict(result) | {
            "issue": issue,
            "builder": f"foundry/{__version__}",
            "models": {"coder": cfg.coder_model, "reviewer": cfg.reviewer_model},
            "started": started,
            "finished": time.time(),
        }
        with ledger.open("a") as f:
            f.write(json.dumps(record) + "\n")
