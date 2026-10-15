"""Who decides whether a tool call runs: permission rules, then hooks.

Rules name a tool and a glob over its target: read(src/**), edit(.github/**), run(python -m pytest*). They are
evaluated deny, then ask, then allow; the first list with a match decides, and anything unmatched asks. In an
unattended run nobody can answer, so ask means no. Hooks are commands from the original repository's config: they
receive the call as JSON on stdin, and exit code 2 blocks it with their stderr as the reason.

Rules over command text guide an honest agent; they are not a sandbox. Real isolation is the sandbox prefix.
"""

import json
import subprocess  # nosec B404
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path


@dataclass
class Verdict:
    allowed: bool
    reason: str


def decide(cfg, tool: str, target: str) -> str:
    call = f"{tool}({target})"
    for verdict, rules in (("deny", cfg.deny), ("ask", cfg.ask), ("allow", cfg.allow)):
        if any(fnmatchcase(call, rule) for rule in rules):
            return verdict
    return "ask"


def check(cfg, tool: str, target: str, cwd: Path, unattended: bool = True) -> Verdict:
    verdict = decide(cfg, tool, target)
    if verdict == "deny":
        return Verdict(False, f"denied by policy: {tool}({target})")
    if verdict == "ask" and unattended:
        return Verdict(False, f"{tool}({target}) needs a person's approval, and this run is unattended")
    payload = json.dumps({"tool": tool, "target": target})
    for hook in cfg.hooks:
        done = subprocess.run(  # nosec B602
            hook, shell=True, check=False, cwd=cwd, input=payload, capture_output=True, text=True, timeout=30
        )
        if done.returncode == 2:
            return Verdict(False, f"blocked by hook: {done.stderr.strip() or hook}")
    return Verdict(True, verdict)
