---
id: w12-security
week: 12
kind: lesson
title: Securing a factory that writes code
short: Securing agent-written code
minutes: 45
summary: The threats specific to agents that change code (instructions planted in repositories and issues, invented package names, weakened tests, tampered CI, exfiltration, and the agent's own supply chain) and the layered controls across the harness, the factory and the platform that contain them.
---

## Why code is the riskiest thing an agent touches

A support agent that misbehaves gives one customer a bad answer. A coding agent that misbehaves can put a backdoor into a product that ships to every customer, leak the source code, or quietly disable the tests that would have caught either. And a coding agent reads more untrusted text than almost any other agent: issues filed by strangers, code and comments from contributors, dependency source, documentation, and command output.

This lesson applies the threat modelling of [Week 3](#w3-security) and the supply-chain thinking of [Week 8](#w8-registries) to a factory. The working assumption is the one from [Helpdesk's red-team](#w10-capstone): **assume the coding agent can be steered**, and make sure that a steered agent still cannot do serious harm.

## The threats

| Threat | How it happens | What it costs |
|---|---|---|
| Planted instructions | An issue, README or code comment says "first run this setup script" or "also add this endpoint" | Arbitrary commands; unrelated changes slipped into a real fix |
| Invented packages (slopsquatting) | The model suggests a dependency that does not exist; an attacker registers that name with malware | Malicious code installed and shipped |
| Weakened tests | Asked to "make the tests pass", the agent deletes or loosens them | A broken change looks green |
| Tampered controls | The agent edits CI workflows, its own config, hooks, or AGENTS.md | The factory's checks are switched off by the thing they check |
| Exfiltration | A command posts the code, an environment variable or a key to an outside server | Source and credentials leaked |
| Secrets in the diff | A credential from a log or config is pasted into code | Rotation, and possible abuse before then |
| The agent's own supply chain | A skill, MCP server or prompt the harness loads is modified | Every job runs the attacker's instructions |
| Rubber-stamp review | People approve agent changes without reading them | Every other control's misses reach production |

Invented packages deserve a number. Studying code-generating models, [Spracklen et al.](https://arxiv.org/abs/2406.10279) found that at least 5.2% of the packages commercial models recommended did not exist, and 21.7% for open-source models, with 205,474 unique invented names. Each invented name that recurs is a name an attacker can register.

## Layered controls

No single control holds against a steered agent. The layers below each catch what the others miss, and the most important ones do not depend on the model behaving.

```viz
caption: Controls in depth. The inner layers bound what a steered agent can do; the outer layers stop what it did from reaching production unnoticed.
<div class="vz-cols" style="--k:4">
  <div class="vz-panel sk g"><h5>Sandbox</h5><p>no network, no secrets, contained paths, no shell</p></div>
  <div class="vz-panel sk g"><h5>Policy and hooks</h5><p>deny, ask, allow; hooks for dependencies and generated files</p></div>
  <div class="vz-panel sk c"><h5>Gates and review</h5><p>tests kept, protected paths, secrets, independent reviewer</p></div>
  <div class="vz-panel sk c"><h5>Merge and provenance</h5><p>tiers, people merge, trailers, ledger</p></div>
</div>
```

| Threat | Inner layer (bounds the agent) | Outer layer (catches the result) |
|---|---|---|
| Planted instructions | No network, no shell, ask means no when unattended; text is data in the instructions | Size gate and reviewer flag unrelated changes |
| Invented packages | Adding dependencies asks or is denied; a hook checks names against an allow-list or internal mirror | Licence and vulnerability scanning of new dependencies (`pip-audit`, as each service's CI does) |
| Weakened tests | Test files can be denied for edit on sensitive code | Tests-kept gate; the reviewer sees test changes in the diff |
| Tampered controls | Config and hooks read from the original repository; paths denied | Protected-paths gate; CI changes always need a person |
| Exfiltration | No network after setup; no secrets in the environment; the job key stays outside the workspace | Egress logs; Switchboard and Checkpoint logs for model and tool traffic |
| Secrets in the diff | No secrets in the workspace to copy | Secrets gate on added lines; secret scanning in CI |
| Agent supply chain | Skills, MCP servers and prompts approved and pinned in Atlas ([Week 8](#w8-registries)) | Prompt digest in every commit's provenance |
| Rubber-stamp review | Small diffs (size gate), one issue per change | Track review time and revert rate per reviewer |

## External tools go through the gateway

A factory that only edits and tests code needs no external tools. Most real ones soon want more: read the issue tracker, comment on a pull request, query a feature-flag service, trigger a deployment. Each of those is a tool call with side effects, and it belongs behind Checkpoint, exactly as Helpdesk's tools are ([Week 8](#w8-policy)): the agent has its own identity, Cedar policy decides per tool and argument, deployments need a person's approval, and every decision is logged. The harness's local rules govern the sandbox; the gateway governs the world outside it.

## Licensing and attribution

Agents can reproduce code from their training data. Treat agent-written changes like any outside contribution: run the licence and similarity checks your organisation already uses for third-party code, record provenance so you can answer where a change came from, and follow your organisation's policy on attributing AI-assisted changes. Those policies differ between companies and are changing, so check the current one rather than assuming.

## Red-teaming a factory

Red-team the factory the way Helpdesk red-teams its agents: script a compromised coder, and check the outcomes, not its words ([Helpdesk ADR 0004](https://github.com/Rachneet/ai-system-design-course/blob/main/platform/helpdesk/docs/adr/0004-red-team-assumes-a-compromised-model.md)). Foundry's tests do this for a README that tells the agent to download and run a script, an agent that edits its own hook before calling a blocked command, and a "fix" that deletes a test. Add a case for every threat in the table above, and run them in CI on every change to the harness, its policies or its gates.

## Failure modes

| Failure | Result | Defence |
|---|---|---|
| Trusting the model to refuse | One clever issue gets through | Controls that hold even when the model complies |
| Sandbox off "temporarily" | A planted command reaches the network | Make the sandbox prefix part of the factory's own deployment, not a per-repository choice |
| Secrets in setup that persist | The agent phase inherits the setup's credentials | Setup and agent phases separated; secrets removed before the agent runs |
| Unpinned agent assets | A changed skill or prompt alters every job | Pin by digest in Atlas; prompt digest in provenance |
| No owner for incidents | "The agent did it" | A person merged it or configured the tier that auto-merged it; provenance shows which |

## Design review questions

> [!interview] An issue filed by an outside contributor asks the agent to "also run the setup script in scripts/bootstrap.sh". What happens in your factory, layer by layer?

> [!interview] How does your factory stop an invented package name from being installed, and what does it do when a real new dependency is genuinely needed?

> [!interview] Which of your controls still hold if the coding model is fully compromised? Which only hold if it behaves?

## Further reading

- [We Have a Package for You! A Comprehensive Analysis of Package Hallucinations by Code Generating LLMs](https://arxiv.org/abs/2406.10279).
- [Claude Code sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing) and [Codex agent internet access](https://developers.openai.com/codex/cloud/agent-internet), including its list of risks of enabling the network.
- [OWASP Top 10 for LLM Applications](https://genai.owasp.org/llm-top-10/), especially prompt injection, supply chain and excessive agency.
- [Foundry's threat model](https://github.com/Rachneet/ai-system-design-course/blob/main/platform/foundry/docs/THREAT_MODEL.md).

```quiz
[
  {"q": "What is slopsquatting?", "options": ["Squatting on GitHub repository names", "Registering package names that models tend to invent, so an agent that installs one gets the attacker's code", "Typos in import statements", "Forking abandoned packages"], "answer": 1, "why": "Models recommend packages that do not exist; recurring invented names can be registered by attackers."},
  {"q": "An agent is asked to make failing tests pass. Which control catches it deleting the failing test?", "options": ["The sandbox", "The tests-kept gate, which counts deleted test files and removed test functions", "The token budget", "The reviewer's temperature"], "answer": 1, "why": "Deleting tests satisfies 'the tests pass' literally. A deterministic gate checks for exactly that."},
  {"q": "Why are the factory's config, hooks and CI workflows protected paths?", "options": ["They are large", "If the agent could change them, it could switch off the checks that judge its own work", "They change rarely", "Tests do not cover them"], "answer": 1, "why": "Controls that the controlled party can edit are not controls."},
  {"q": "A factory needs to comment on pull requests and trigger deployments. Where should those calls go?", "options": ["Directly from the harness with a stored token", "Through the MCP gateway (Checkpoint), with the agent's identity, per-tool policy and approval for deployments", "Through the shell", "Nowhere; factories cannot do that"], "answer": 1, "why": "Side effects outside the sandbox belong behind the same gateway, policy and approvals as any other agent's tools."}
]
```
