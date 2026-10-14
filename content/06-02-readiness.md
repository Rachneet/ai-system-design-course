---
id: w6-readiness
week: 6
kind: lesson
title: Validating security, reliability, and production readiness
short: Production readiness
minutes: 45
summary: A production readiness review for AI systems, a checklist across quality, security, privacy, reliability, operations, and cost, and how to verify each item with evidence instead of assertions.
---

## Readiness is evidence, not confidence

"We think it's ready" is not a launch criterion. A **production readiness review** (PRR) checks that each risk area has a control and that the control has been **verified**: a test, a drill, a measurement, a log. The checklist below is the one to run on your capstone. Each item says how to prove it.

## Quality

| Item | Evidence |
|---|---|
| Eval suite reflects real traffic | Source breakdown (traces, bugs, synthetic, red-team); category distribution vs production |
| Category pass rates meet targets | Latest release-suite report, pass^k for critical flows |
| Judges calibrated | Kappa and per-class recall on held-out human labels |
| Held-out set passes | Report from a run on cases not used during tuning |
| Online quality monitoring live | Dashboard with judge pass rates and resolution rate |
| Feedback → dataset loop works | At least one case added from production feedback |

## Security

| Item | Evidence |
|---|---|
| Authentication on every endpoint | Automated test: each route without a token returns 401 |
| Authorization in every tool | Tests: cross-customer access returns not-found for every read and write tool |
| Business limits enforced in code | Unit tests on tool limits independent of the model |
| Lethal trifecta assessed per workflow | Threat model table; which leg is removed for each |
| Red-team suite passes must-never gate | Report with attack success rate by category |
| Untrusted content isolated | Design + test: review/email injection cases |
| Output channels closed | Test: Markdown images and external links are not rendered |
| Secrets managed | No secrets in repo (scanner output); secret manager config; key per environment with spend cap |
| Dependencies and image scanned | Scanner report with no unresolved critical CVEs |
| Third-party MCP servers reviewed | List with versions, permissions, and who reviewed them |

## Privacy and data

| Item | Evidence |
|---|---|
| Data inventory | Table of what personal data is stored where (sessions, messages, memories, traces, logs, vectors) |
| Retention defined and enforced | Scheduled deletion jobs, with a test |
| Deletion requests work end to end | Drill: delete a test user; verify DB, memories, vectors, traces, caches |
| PII redaction in traces and logs | Sample of exported spans showing redaction |
| Tenant isolation | RLS or equivalent; test that queries without tenant context return nothing |
| Provider data terms understood | Notes on model provider retention and training policies for your account |

## Reliability

| Item | Evidence |
|---|---|
| SLOs defined | SLO doc with SLIs and targets |
| Timeouts layered correctly | Config showing platform > agent > tool > model timeouts |
| Retries bounded, with jitter, no multiplied layers | Code review + test |
| Idempotent writes | Tests: duplicate job and duplicate request produce one refund |
| Fallback model tested | Eval run on the fallback; game-day result |
| Circuit breaker | Test with injected failures |
| Graceful degradation | Demo with provider failure injected |
| Load tested at 2x expected peak | Load test report: latency, errors, rate-limit headroom |
| Backups restorable | Restore drill with timestamp |
| Graceful shutdown | Deploy during load test shows no dropped streams |

## Operations

| Item | Evidence |
|---|---|
| Tracing end to end | A trace spanning API, worker, and MCP server |
| Dashboards | Screenshot or link for health, cost, behaviour, quality, capacity |
| Alerts with runbooks | Alert list, each linked to a runbook |
| Kill switches tested | Date and result of last flip for each |
| Rollback practiced | Time to roll back from the last drill |
| On-call defined | Who is paged, escalation path |
| Prompt and model versions traceable | Trace attributes include prompt SHA and model ID |

## Cost

| Item | Evidence |
|---|---|
| Cost per conversation measured | Dashboard p50/p95/p99 |
| Budget alerts | Provider and cloud budget alerts configured |
| Per-user and per-tenant limits | Tests showing 429 and budget cut-off |
| 10x projection | Cost model in design doc |
| Dashboard matches invoice | Reconciliation within 5% |

## Load testing an AI system

Load tests for LLM apps have a twist: real model calls at load cost real money and hit real rate limits. Strategies:

- **Mock the model** at the HTTP layer with a fake server that streams tokens with realistic latency distributions. Tests your API, database, queues, and autoscaling cheaply.
- **Short real-model test** at expected peak for a few minutes to measure true provider latency and rate-limit headroom, within an agreed budget.
- **Simulate realistic conversations** (multi-turn, with tool calls), not a single repeated request, or caches will flatter you.

Tools such as k6 or Locust work well; drive them with your Week 3 simulator's conversation scripts.

## Pre-mortem

Before launch, run a 30-minute **pre-mortem**: "It is three months from now and this launch was a disaster. What happened?" Everyone writes failure stories independently, then you group them. Typical answers for agent launches: the agent gave a wrong refund policy for weeks because a KB article was outdated; one tenant's bulk usage hit rate limits for everyone; an injection in a review triggered refunds; costs tripled after a model upgrade changed verbosity. Each story either maps to an existing control in the checklist, or becomes an action item.

## Launch plan

- **Staged rollout**: internal staff → 1% → 10% → 50% → 100%, with explicit metrics and a hold period at each stage.
- **Human in the loop at first**: for high-risk actions, require approval for everyone during the first weeks, then relax based on measured error rates.
- **Launch-day roles**: who watches which dashboard, who can flip which switch.

## Design review questions

> [!interview] Pick any checklist item marked done. Show me the evidence.

> [!interview] What did your pre-mortem find that was not already covered?

> [!interview] What is your rollout plan, and what metric moves you from 10% to 50%?

## Further reading

- [OWASP Top 10 for LLM Applications](https://genai.owasp.org/llm-top-10/), as a security checklist.
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework), for governance language and structure.
- [AWS Well-Architected Generative AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/generative-ai-lens.html).
- [Google SRE book](https://sre.google/sre-book/table-of-contents/), especially the chapters on launch coordination and postmortems.
- [What We Learned from a Year of Building with LLMs](https://applied-llms.org/), the operational section.

```quiz
[
  {"q": "What turns a readiness checklist item from \"claimed\" into \"done\"?", "options": ["A team vote", "Evidence: a test, drill, measurement, or log that verifies the control", "Manager sign-off", "A passing build"], "answer": 1, "why": "Readiness is about verified controls, not confidence."},
  {"q": "How can you load test an LLM app without spending heavily on tokens?", "options": ["You cannot", "Mock the model API with a fake server that streams with realistic latency, then run a short, budgeted real-model test", "Use a single repeated request", "Test only in production"], "answer": 1, "why": "A fake model tests your own infrastructure cheaply; a short real test measures provider latency and limits."},
  {"q": "What is a pre-mortem?", "options": ["A postmortem written in advance for compliance", "An exercise imagining the launch failed and listing why, to find uncovered risks", "A load test", "A rollback plan"], "answer": 1, "why": "It surfaces risks people sense but have not raised, and maps them to controls."}
]
```
