---
id: w6-readiness
week: 6
kind: lesson
title: Validating security, reliability, and production readiness
short: Production readiness
minutes: 50
summary: A production readiness review for AI systems, a checklist across quality, security, privacy, reliability, operations, and cost, and how to verify each item with evidence instead of assertions.
---

## Readiness is evidence, not confidence

"We think it's ready" is not a launch criterion. A **production readiness review** (PRR) checks that each risk area has a control and that the control has been **verified**: a test, a drill, a measurement, a log. The checklist below is the one to run on your capstone. Each item says how to prove it.

```viz
caption: A box is ticked only when someone can show the evidence. One claimed but unproven box keeps its whole area red.
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk g"><h5>Quality: ready</h5>
    <div class="vz-row"><span class="ch sk g">&#10003;</span><span style="flex:1 1 0;min-width:0">release suite report</span></div>
    <div class="vz-row"><span class="ch sk g">&#10003;</span><span style="flex:1 1 0;min-width:0">judge kappa on labels</span></div>
  </div>
  <div class="vz-panel sk b"><h5>Security: not ready</h5>
    <div class="vz-row"><span class="ch sk g">&#10003;</span><span style="flex:1 1 0;min-width:0">401 test on every route</span></div>
    <div class="vz-row"><span class="ch sk ghost">?</span><span style="flex:1 1 0;min-width:0">"we red-teamed it"</span></div>
  </div>
  <div class="vz-panel sk g"><h5>Reliability: ready</h5>
    <div class="vz-row"><span class="ch sk g">&#10003;</span><span style="flex:1 1 0;min-width:0">fallback model eval run</span></div>
    <div class="vz-row"><span class="ch sk g">&#10003;</span><span style="flex:1 1 0;min-width:0">restore drill, dated</span></div>
  </div>
  <div class="vz-panel sk b"><h5>Privacy: not ready</h5>
    <div class="vz-row"><span class="ch sk ghost">?</span><span style="flex:1 1 0;min-width:0">"deletion works"</span></div>
    <div class="vz-row"><span class="ch sk g">&#10003;</span><span style="flex:1 1 0;min-width:0">redacted span sample</span></div>
  </div>
  <div class="vz-panel sk g"><h5>Operations: ready</h5>
    <div class="vz-row"><span class="ch sk g">&#10003;</span><span style="flex:1 1 0;min-width:0">kill switch flipped</span></div>
    <div class="vz-row"><span class="ch sk g">&#10003;</span><span style="flex:1 1 0;min-width:0">rollback timed</span></div>
  </div>
  <div class="vz-panel sk g"><h5>Cost: ready</h5>
    <div class="vz-row"><span class="ch sk g">&#10003;</span><span style="flex:1 1 0;min-width:0">dashboard vs invoice</span></div>
    <div class="vz-row"><span class="ch sk g">&#10003;</span><span style="flex:1 1 0;min-width:0">429 on budget test</span></div>
  </div>
</div>
<div class="vz-row"><span class="ch sk g">&#10003;</span><span>evidence: a test, drill, measurement or log</span><span class="ch sk ghost">?</span><span style="flex:1 1 0;min-width:0">a claim: not done yet</span></div>
```

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
| Provider data terms understood | Notes on retention and training policies for every provider and gateway in the request path (a router such as OpenRouter is one more party that sees the data) |

## Reliability

| Item | Evidence |
|---|---|
| SLOs defined | SLO doc with SLIs and targets |
| Timeouts layered correctly | Config showing platform > agent > tool > model timeouts |
| Retries bounded, with jitter, no multiplied layers | Code review + test |
| Idempotent writes | Tests: duplicate job and duplicate request produce one refund |
| Fallback model tested | Eval run on the fallback (a second provider, or an open-weights model on vLLM or Ollama, behind the same interface); game-day result |
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
| Prompt and model versions traceable | Trace attributes include prompt SHA, provider, and pinned model ID (a dated snapshot, not a moving alias) |

## Cost

| Item | Evidence |
|---|---|
| Cost per conversation measured | Dashboard p50/p95/p99 |
| Budget alerts | Budget alerts at every provider, at the gateway (LiteLLM and similar proxies support per-key budgets), and on GPU spend if you self-host |
| Per-user and per-tenant limits | Tests showing 429 and budget cut-off |
| 10x projection | Cost model in design doc |
| Dashboard matches invoice | Reconciliation within 5% |

## Load testing an AI system

Load tests for LLM apps have a twist: real model calls at load cost real money and hit real rate limits. Strategies:

- **Mock the model** at the HTTP layer with a fake server that streams tokens with realistic latency distributions. Tests your API, database, queues, and autoscaling cheaply. Because OpenAI, Gemini, vLLM, Ollama, OpenRouter and most gateways accept the same OpenAI-compatible chat format, one fake server that speaks it covers most setups; add a second shape only if you call a provider's native API.
- **Short real-model test** at expected peak for a few minutes to measure true provider latency and rate-limit headroom, within an agreed budget. If you self-host, this is where you measure goodput: requests per second that still meet your TTFT and TPOT targets (see the [inference lesson](#w5-inference)).
- **Simulate realistic conversations** (multi-turn, with tool calls), not a single repeated request, or caches will flatter you.

Tools such as k6 or Locust work well; drive them with your Week 3 simulator's conversation scripts.

## Pre-mortem

Before launch, run a 30-minute **pre-mortem**: "It is three months from now and this launch was a disaster. What happened?" Everyone writes failure stories independently, then you group them. Typical answers for agent launches: the agent gave a wrong refund policy for weeks because a KB article was outdated; one tenant's bulk usage hit rate limits for everyone; an injection in a review triggered refunds; costs tripled after a model upgrade changed verbosity. Each story either maps to an existing control in the checklist, or becomes an action item.

## Launch plan

- **Staged rollout**: internal staff → 1% → 10% → 50% → 100%, with explicit metrics and a hold period at each stage.

```viz
caption: Each stage is a gate. Traffic moves up only after the metric holds for the hold period, and a tripped guardrail sends it straight back to zero.
<div class="vz-bars"><span>staff</span><span class="bar sk"><i class="sk c" style="--w:1%"></i></span><b>internal</b><span>stage 1</span><span class="bar sk"><i class="sk c" style="--w:1%"></i></span><b>1%</b><span>stage 2</span><span class="bar sk"><i class="sk c" style="--w:10%"></i></span><b>10%</b><span>stage 3</span><span class="bar sk"><i class="sk c" style="--w:50%"></i></span><b>50%</b><span>stage 4</span><span class="bar sk"><i class="sk c" style="--w:100%"></i></span><b>100%</b></div>
<div class="vz-cols">
  <div class="vz-panel sk g"><h5>Move up when</h5><p>resolution rate and cost hold for the whole hold period</p></div>
  <div class="vz-panel sk b"><h5>Roll back when</h5><p>a guardrail trips: wrong refunds, complaints, error rate</p></div>
</div>
```
- **Human in the loop at first**: for high-risk actions, require approval for everyone during the first weeks, then relax based on measured error rates.
- **Launch-day roles**: who watches which dashboard, who can flip which switch.

## Design review questions

> [!interview] Pick any checklist item marked done. Show me the evidence.

> [!interview] What did your pre-mortem find that was not already covered?

> [!interview] What is your rollout plan, and what metric moves you from 10% to 50%?

## Further reading

- [OWASP Top 10 for LLM Applications](https://genai.owasp.org/llm-top-10/), as a security checklist.
- [Purple Llama](https://github.com/meta-llama/PurpleLlama), Meta's open safety tools (Llama Guard, Prompt Guard, CyberSecEval): model-agnostic classifiers and benchmarks you can cite as guardrail and red-team evidence.
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
