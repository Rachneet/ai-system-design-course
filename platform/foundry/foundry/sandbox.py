"""The workspace an agent works in: a throwaway clone of the repository, never the original.

What this enforces itself: paths stay inside the clone (symlinks included), commands run without a shell (so no
pipes, `&&` or `$(...)` to smuggle a second command past the policy), with an environment that carries no secrets,
a time limit and an output limit. What it cannot enforce in-process is network and filesystem isolation for the
command itself: set `sandbox_prefix` to an OS sandbox (bubblewrap on Linux, sandbox-exec on macOS, or a container)
for that. See ADR 0001.
"""

import os
import shlex
import shutil
import subprocess  # nosec B404
import tempfile
from dataclasses import dataclass
from pathlib import Path

MAX_OUTPUT = 8_000


class SandboxError(Exception):
    pass


@dataclass
class Ran:
    code: int
    output: str


def git(cwd: Path, *args: str, env: dict | None = None) -> str:
    run_env = os.environ | env if env else None
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=run_env).stdout  # nosec B603 B607


class Workspace:
    def __init__(self, root: Path, prefix: list[str], timeout_s: int):
        self.root, self.prefix, self.timeout_s = root.resolve(), prefix, timeout_s

    @classmethod
    def clone(cls, source: Path, prefix: list[str] | None = None, timeout_s: int = 120) -> "Workspace":
        root = Path(tempfile.mkdtemp(prefix="foundry-")) / "repo"
        git(source, "clone", "--quiet", "--no-hardlinks", str(source.resolve()), str(root))
        return cls(root, prefix or [], timeout_s)

    def path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if not p.is_relative_to(self.root):
            raise SandboxError(f"{rel} is outside the workspace")
        return p

    def run(self, command: str) -> Ran:
        try:
            argv = self.prefix + shlex.split(command)
        except ValueError as e:
            return Ran(2, f"could not parse the command: {e}")
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.root), "LANG": "C.UTF-8"}
        try:
            done = subprocess.run(  # nosec B603
                argv, check=False, cwd=self.root, env=env, capture_output=True, text=True, timeout=self.timeout_s
            )
        except FileNotFoundError:
            return Ran(127, f"command not found: {argv[0]}")
        except subprocess.TimeoutExpired:
            return Ran(124, f"timed out after {self.timeout_s} s")
        out = done.stdout + done.stderr
        if len(out) > MAX_OUTPUT:
            out = (
                out[: MAX_OUTPUT // 2]
                + f"\n[... {len(out) - MAX_OUTPUT} characters cut ...]\n"
                + out[-MAX_OUTPUT // 2 :]
            )
        return Ran(done.returncode, out)

    def diff(self) -> str:
        git(self.root, "add", "--all")
        return git(self.root, "diff", "--cached")

    def changed(self) -> list[tuple[str, str]]:
        """(status, path) for every staged change: A added, M modified, D deleted, R renamed."""
        git(self.root, "add", "--all")
        lines = git(self.root, "diff", "--cached", "--name-status").splitlines()
        return [(line.split("\t")[0][0], line.split("\t")[-1]) for line in lines if line]

    def remove(self) -> None:
        shutil.rmtree(self.root.parent, ignore_errors=True)
