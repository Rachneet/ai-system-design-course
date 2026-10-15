import json
import subprocess
from itertools import count

import httpx
import pytest

from foundry.config import Config
from foundry.model import Model

_ids = count(1)
BUGGY = "def add(a, b):\n    return a - b\n"
TESTS = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n\n\ndef test_add_zero():\n    assert add(0, 4) == 4\n"


def git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True
    )


@pytest.fixture
def repo(tmp_path):
    """A repository with a bug the tests catch."""
    r = tmp_path / "repo"
    (r / "tests").mkdir(parents=True)
    (r / "calc.py").write_text(BUGGY)
    (r / "tests" / "test_calc.py").write_text(TESTS)
    (r / "conftest.py").write_text("")
    git(r, "init", "--quiet", "--initial-branch=main")
    git(r, "add", "--all")
    git(r, "commit", "--quiet", "-m", "start")
    return r


def calls(*items):
    return [{"name": n, "args": a} for n, a in items]


class Scripted:
    """Answers chat completions from a script per role (the role is the last part of x-switchboard-tag)."""

    def __init__(self):
        self.script: dict[str, list] = {"coder": [], "reviewer": []}
        self.seen: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        role = request.headers["x-switchboard-tag"].rsplit(":", 1)[-1]
        self.seen.append({"role": role, "body": body, "auth": request.headers["authorization"]})
        step = self.script.get(role, []).pop(0) if self.script.get(role) else "nothing left to say"
        if isinstance(step, str):
            message = {"role": "assistant", "content": step}
        else:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"c{next(_ids)}",
                        "type": "function",
                        "function": {"name": c["name"], "arguments": json.dumps(c["args"])},
                    }
                    for c in step
                ],
            }
        return httpx.Response(200, json={"choices": [{"message": message}], "usage": {"total_tokens": 1000}})


@pytest.fixture
def scripted():
    return Scripted()


@pytest.fixture
def model(scripted):
    return Model("http://switchboard", "sbk_job_key", transport=httpx.MockTransport(scripted))


@pytest.fixture
def cfg():
    return Config(switchboard_key="sbk_job_key")


FIX = [
    calls(("read_file", {"path": "calc.py"})),
    calls(("edit_file", {"path": "calc.py", "old": "return a - b", "new": "return a + b"})),
    calls(("run", {"command": "python -m pytest -q"})),
    calls(("finish", {"summary": "Fix add: it subtracted instead of adding"})),
]
APPROVE = '{"approve": true, "reasons": ["fixes the bug, nothing else changed"]}'
