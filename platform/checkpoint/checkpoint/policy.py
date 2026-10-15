"""Cedar policy: who may call which tool, with which arguments, for which user, and when a human must approve.

Entities: Agent::"<id>" is the principal, Tool::"<server>__<tool>" the resource, and the actions are
Action::"list" (the tool appears in tools/list) and Action::"call". The request context carries
{args, user: {id, roles}, server}. Cedar denies by default and any matching forbid wins.

A permit annotated @approval("required") allows the call only after a person approves that exact call.
Every decision names the policies that produced it, by their @id annotation, for the audit log.
"""

import json
from dataclasses import dataclass, field

import cedarpy


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
        self.annotations = {pid: p.get("annotations", {}) for pid, p in parsed.get("staticPolicies", {}).items()}

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
        errors = [str(e) for e in r.diagnostics.errors]
        if not r.allowed:
            return Decision(False, policies=[self.name(p) for p in reasons], errors=errors)
        approval = any(self.annotations.get(p, {}).get("approval") == "required" for p in reasons)
        return Decision(True, approval, [self.name(p) for p in reasons], errors)
