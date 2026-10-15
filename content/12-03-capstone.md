---
id: w12-capstone
week: 12
kind: lab
title: "Final capstone: a software factory for a real repository"
short: "Capstone: software factory"
minutes: 600
summary: Run a software factory on a repository you know, with your own harness controls, gates, reviewer, merge tiers and provenance, and prove it with an eval suite built from history, a red-team suite against a compromised coder, and cost and review numbers per merged change.
---

## The brief

Build and run a **software factory** for one real repository you work on, or a substantial open-source one you can fork. Issues go in; tested and reviewed branches come out; a person merges anything outside an auto-merge tier you can justify. Every model call goes through Switchboard, every external tool call through Checkpoint, and the factory's prompts, skills and MCP servers are approved in Atlas.

The [Week 10 capstone](#w10-capstone) asked you to run agents that serve people. This one asks you to run agents that change the system itself, and to prove that doing so is safe, measured and worth it.

## Required components

| # | Component | Minimum |
|---|---|---|
| 1 | **Harness** | Tools with result limits, a step limit and a per-job budget; deny, ask and allow rules (ask means no when unattended); at least two hooks; an OS sandbox with no network after setup |
| 2 | **Context** | An AGENTS.md for the repository, measured: pass^k on your suite with and without it |
| 3 | **Gates** | Tests, size, protected paths, tests kept and secrets, plus at least one gate specific to your stack (types, lint, migrations, licences) |
| 4 | **Reviewer** | Independent (issue and diff only), a different model from the coder, a fixed output that fails closed, calibrated against at least 20 human reviews |
| 5 | **Merge tiers** | A written policy of which change types may auto-merge, and the eval evidence for each |
| 6 | **Provenance** | Trailers on every commit and a ledger record per job; a query that lists every change from one job, one model, or one prompt digest |
| 7 | **External tools** | Anything beyond the sandbox (tracker, forge, deployment) through Checkpoint, with deployments held for approval |
| 8 | **Evals** | At least 15 tasks from your repository's history, each proven real (fails before, passes with the fix), run with at least 3 trials |
| 9 | **Red-team** | At least 10 compromised-coder cases covering the threats in [this week's security lesson](#w12-security), in CI |
| 10 | **Economics** | Cost per merged change from Switchboard's ledger joined to outcomes, review time per change, and change failure rate over the test period |

## Phased plan

```viz
caption: Prove the controls before you scale the throughput. Every phase ends with something you can show, not describe.
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk"><h5>1. Harness, days 1 to 3</h5><p>one issue fixed in a sandbox; rules and hooks proven</p></div>
  <div class="vz-panel sk c"><h5>2. Evals, days 4 to 6</h5><p>15 tasks from history, proven real; a baseline pass^k</p></div>
  <div class="vz-panel sk c"><h5>3. Factory, days 7 to 9</h5><p>gates, reviewer, tiers, provenance</p></div>
  <div class="vz-panel sk c"><h5>4. Red-team, days 10 to 11</h5><p>compromised coder; zero harmful outcomes</p></div>
  <div class="vz-panel sk g"><h5>5. Run it, days 12 to 14</h5><p>real issues; cost, review time, failures</p></div>
</div>
```

**Phase 1 accept when:** an issue is fixed in a sandboxed clone with no network, every tool call appears in the transcript with the rule that allowed it, a deny rule and a hook each block a call, and the job's model cost appears in Switchboard under its `job:` tag.

**Phase 2 accept when:** at least 15 tasks pass the "is it real" check, and you have a baseline pass@1 and pass^k (k = 3) for your harness and model, plus the same with a second model through Switchboard.

**Phase 3 accept when:** a change that deletes a test, one that touches a protected path, and one the reviewer refuses are each rejected with reasons; an accepted change carries trailers and a ledger record; your provenance query works.

**Phase 4 accept when:** every red-team case ends with no harmful change merged, no network reached and no secret exposed, including a planted setup script, an invented package, a self-edited hook, a weakened test and a CI change.

**Phase 5 accept when:** at least 10 real issues have run through the factory, with acceptance rate, review time per merged change, cost per merged change and any reverts reported, and a decision, with reasons, on whether the factory pays for this repository.

## Review rubric

| Area | Excellent (4) | Adequate (2) | Missing (0) |
|---|---|---|---|
| Harness controls | Sandbox with no network, rules and hooks proven by tests, config out of the agent's reach | Rules and a sandbox, partly tested | Prompts as the only control |
| Evals | 15+ tasks from history, proven real, pass^k across two models | Tasks exist, partly validated | Public leaderboard numbers only |
| Gates and review | Deterministic gates first, an independent and calibrated reviewer, fails closed | Gates or a reviewer, not both | Merge on "tests pass" claimed by the agent |
| Merge policy | Tiers justified by eval evidence; people own sensitive changes | A default policy | Everything auto-merges, or nothing is decided |
| Provenance | Trailers, ledger and a working query | Ledger only | None |
| Security | Red-team suite in CI with zero harmful outcomes | Some cases | None |
| Economics | Cost and review time per merged change, with a decision | Model cost only | None |
| Communication | Clear demo, honest about what failed | Understandable | Unclear |

A total of 24 or more out of 32 is a strong portfolio project.

## What to present (20 minutes plus 10 of questions)

1. **The repository and why a factory** (2 min).
2. **Live demo** (6 min): an issue to a reviewed branch; a planted instruction that gets nowhere; a rejected change and why; a provenance query.
3. **Evidence** (7 min): eval results over two models, red-team results, cost and review time per merged change.
4. **Decisions and trade-offs** (4 min): your merge tiers and their evidence; what you chose not to automate.
5. **What's next** (1 min).

## What is not required

- A forge integration: local branches are fine, if your provenance and review evidence are complete.
- A planner role, subagents or context compaction, unless your issues need them; record the decision in an ADR.
- Signed attestations: describe how you would add them.

## The reference implementation

[Foundry](https://github.com/Rachneet/ai-system-design-course/tree/main/platform/foundry) is a working baseline: the harness, the six gates, the independent reviewer, branch-and-wait merging, trailers and a ledger, an eval runner with tasks proven real, and 14 tests with a scripted model. Start from it or from scratch. Either way, its ADRs are worth arguing with: a two-layer sandbox, gates before review, branch-and-wait by default, and evals from your own history.

## Reference reading

- This week's lessons: [The software factory](#w12-factory) and [Securing a factory that writes code](#w12-security).
- Last week's: [Inside a coding-agent harness](#w11-harness), [Evaluating coding agents](#w11-evals) and [Lab 11](#w11-lab).
- The [Week 10 capstone](#w10-capstone) for evidence packs, and [AI FinOps](#w10-finops) for unit economics.
