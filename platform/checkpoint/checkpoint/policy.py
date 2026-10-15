"""Cedar policy: who may call which tool, with which arguments, for which user, and when a human must approve.

Entities: Agent::"<id>" is the principal, Tool::"<server>__<tool>" the resource, and the actions are
Action::"list" (the tool appears in tools/list) and Action::"call". The request context carries
{args, user: {id, roles, tenant}, agent: {tenant}, server}. Cedar denies by default and any matching forbid wins.

A permit annotated @approval("required") allows the call only after a person approves that exact call.
Every decision names the policies that produced it, by their @id annotation, for the audit log.

Cedar skips a policy whose condition fails to evaluate (a missing attribute, a type error). For a permit that
fails closed; for a forbid it would fail open, so an allow is turned into a deny when any forbid errored.
"""

import json
import re
from dataclasses import dataclass, field

import cedarpy

ERRORED = re.compile(r"policy `([^`]+)`")


class PolicyError(ValueError):
    pass


@dataclass
class Decision:
    allowed: bool
    needs_approval: bool = False
    policies: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class Policy:
    def __init__(self, text: str):
        try:
            parsed = json.loads(cedarpy.policies_to_json_str(text))
        except ValueError as e:  # cedarpy reports parse errors as ValueError
            raise PolicyError(f"policies do not parse: {e}") from None
        self.text = text
        static = parsed.get("staticPolicies", {})
        self.annotations = {pid: p.get("annotations", {}) for pid, p in static.items()}
        self.forbids = {pid for pid, p in static.items() if p.get("effect") == "forbid"}

    def name(self, pid: str) -> str:
        return self.annotations.get(pid, {}).get("id", pid)

    def decide(self, agent: str, action: str, tool: str, context: dict) -> Decision:
        req = {
            "principal": f'Agent::"{agent}"',
            "action": f'Action::"{action}"',
            "resource": f'Tool::"{tool}"',
            "context": context,
        }
        r = cedarpy.is_authorized(req, self.text, [])
        reasons = list(r.diagnostics.reasons)
        errors = [ERRORED.sub(lambda m: f"policy `{self.name(m[1])}`", str(e)) for e in r.diagnostics.errors]
        if not r.allowed:
            return Decision(False, policies=[self.name(p) for p in reasons], errors=errors)
        broken = [p for e in r.diagnostics.errors for p in ERRORED.findall(str(e)) if p in self.forbids]
        if broken:
            return Decision(False, policies=[self.name(p) for p in broken], errors=errors)
        approval = any(self.annotations.get(p, {}).get("approval") == "required" for p in reasons)
        return Decision(True, approval, [self.name(p) for p in reasons], errors)
