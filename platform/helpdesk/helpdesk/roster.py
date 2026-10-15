"""The agents, from config/agents.toml, their models from config/models.toml, and their instructions from Agent Skills
packages (skills/<name>/SKILL.md). Loading fails loudly on anything inconsistent, such as a handoff to an agent in
another tenant, so a bad roster never starts."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class AgentSpec:
    id: str
    tenant: str
    tier: str
    model: str
    skill: str
    instructions: str
    description: str
    handoffs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Roster:
    agents: dict[str, AgentSpec]
    tenants: dict[str, dict]
    models: dict[str, str]
    risk: dict[str, dict] = field(default_factory=dict)  # per agent: tier, note, NIST AI 600-1 risks

    def triage(self, tenant: str) -> AgentSpec:
        return self.agents[self.tenants[tenant]["triage"]]


def read_skill(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    _, front, body = text.split("---", 2)
    return yaml.safe_load(front), body.strip()


def load(agents_file: str, models_file: str, skills_dir: str) -> Roster:
    spec = tomllib.loads(Path(agents_file).read_text())
    models = tomllib.loads(Path(models_file).read_text())["tiers"]
    agents, problems = {}, []
    for aid, a in spec["agents"].items():
        meta, body = read_skill(Path(skills_dir) / a["skill"] / "SKILL.md")
        if meta.get("name") != a["skill"]:
            problems.append(f"{aid}: skill {a['skill']} declares name {meta.get('name')!r}")
        if a["tier"] not in models:
            problems.append(f"{aid}: unknown model tier {a['tier']}")
        agents[aid] = AgentSpec(
            aid,
            a["tenant"],
            a["tier"],
            models.get(a["tier"], ""),
            a["skill"],
            body,
            a["description"],
            tuple(a.get("handoffs", ())),
        )
    for aid, a in agents.items():
        if a.tenant not in spec["tenants"]:
            problems.append(f"{aid}: unknown tenant {a.tenant}")
        for target in a.handoffs:
            if target not in agents or agents[target].tenant != a.tenant:
                problems.append(f"{aid}: handoff target {target} is not an agent of tenant {a.tenant}")
    for tenant, t in spec["tenants"].items():
        if agents.get(t["triage"], None) is None or agents[t["triage"]].tenant != tenant:
            problems.append(f"tenant {tenant}: triage agent {t['triage']} is missing or belongs elsewhere")
    if problems:
        raise ValueError("invalid roster: " + "; ".join(problems))
    return Roster(agents, spec["tenants"], models, spec.get("risk", {}))
