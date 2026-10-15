"""Settings come from two places. The repository's foundry.toml says how to work on it (test command, protected
paths, permissions, models); it is read from the original repository before a run, so an agent that edits its own
copy cannot loosen its rules. The environment says where the platform is (Switchboard's URL and the job's key)."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    test: str = "python -m pytest -q"
    coder_model: str = "foundry-coder"
    reviewer_model: str = "foundry-reviewer"
    max_steps: int = 30
    max_tokens: int = 400_000  # per job, across every model call
    max_changed_lines: int = 300
    protected: list[str] = field(default_factory=lambda: [".github/**", "foundry.toml", "AGENTS.md"])
    allow: list[str] = field(default_factory=lambda: ["read(**)", "edit(**)", "run(python -m pytest*)"])
    ask: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=lambda: ["edit(.git/**)", "edit(.github/**)", "edit(foundry.toml)"])
    hooks: list[str] = field(default_factory=list)  # commands that get each tool call as JSON; exit 2 blocks it
    sandbox_prefix: list[str] = field(default_factory=list)  # e.g. a bubblewrap or sandbox-exec invocation
    timeout_s: int = 120
    auto_merge: bool = False
    switchboard_url: str = field(default_factory=lambda: os.environ.get("SWITCHBOARD_URL", "http://localhost:8000"))
    switchboard_key: str = field(default_factory=lambda: os.environ.get("FOUNDRY_SWITCHBOARD_KEY", ""), repr=False)


def load(repo: Path) -> Config:
    path = repo / "foundry.toml"
    data = tomllib.loads(path.read_text()).get("foundry", {}) if path.exists() else {}
    unknown = set(data) - set(Config.__dataclass_fields__) - {"switchboard_url", "switchboard_key"}
    if unknown:
        raise ValueError(f"foundry.toml: unknown settings {sorted(unknown)}")
    data.pop("switchboard_key", None)  # never from a file in the repository
    return Config(**data)
