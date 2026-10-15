"""Every eval task is real: its hidden test fails on the code as given and passes with the reference fix."""

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

TASKS = sorted(p for p in (Path(__file__).parents[1] / "evals" / "tasks").iterdir() if (p / "task.toml").exists())


def hidden_passes(task: Path, tmp: Path, reference: bool) -> bool:
    spec = tomllib.loads((task / "task.toml").read_text())
    shutil.copytree(task / "repo", tmp, dirs_exist_ok=True)
    (tmp / "_hidden_test.py").write_text(spec["hidden_test"])
    for path, text in spec["reference"].items() if reference else []:
        (tmp / path).write_text(text)
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "_hidden_test.py"],
        cwd=tmp,
        capture_output=True,
        check=False,
    )
    return run.returncode == 0


@pytest.mark.parametrize("task", TASKS, ids=[t.name for t in TASKS])
def test_task_is_real(task, tmp_path):
    assert not hidden_passes(task, tmp_path / "before", reference=False)
    assert hidden_passes(task, tmp_path / "after", reference=True)
