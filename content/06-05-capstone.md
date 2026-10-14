---
id: w6-lab
week: 6
kind: lab
title: "Capstone: Ship a production-grade AI application"
short: "Capstone"
minutes: 600
builds: Your own deployed, evaluated, monitored AI system
summary: Design, build, evaluate, and present your own production-grade AI application, either Relay taken to launch quality or a new system in a domain you care about, with a design review, a readiness review, and a live demo.
---

## The brief

Ship an AI application that a real user could rely on, and prove it. You can either:

- **Track A: take Relay to launch quality.** Complete every acceptance criterion from Labs 1 to 5, then pass the readiness checklist and present it.
- **Track B: build your own system.** Apply the whole course to a new domain. Pick something you understand, ideally a problem you or someone you know actually has. It is more work and more impressive.

Either way, the bar is the same: a live workflow, real numbers, and evidence for every claim.

## Requirements

Your system must have:

1. **An agentic core** with at least five tools, including at least one write tool with code-enforced limits and a human approval path for high-impact actions.
2. **Retrieval** over a corpus that changes, with incremental updates and access control enforced before generation.
3. **Memory** (short-term sessions in a shared store; long-term memory if your use case benefits).
4. **Guardrails** on input, output, and tool calls, each with a measured precision and recall on a labelled set.
5. **An eval suite** of at least 150 cases from at least three sources, with calibrated judges, a red-team set, and a CI gate.
6. **Deployment** to a cloud environment behind authentication, through a pipeline, with staging and rollback.
7. **Observability**: end-to-end traces, cost and quality dashboards, online evaluation, alerts with runbooks, and tested kill switches.
8. **A design doc** with ADRs, a cost model, and a threat model.

Any model provider works. Use a hosted API (OpenAI, Anthropic, Google Gemini, Mistral), an open-weights model (Llama, Qwen, DeepSeek, Mistral) served with vLLM or Ollama, or a router such as OpenRouter, LiteLLM or Hugging Face Inference Providers. Most of these accept the same OpenAI-compatible chat format, so keep every model call behind one small interface: then your fallback model, your eval runs on a second model, and a later switch are each a config change.

## Project ideas for Track B

All original prompts; pick one or bring your own.

| Project | Core challenge | Write action needing control |
|---|---|---|
| **Clinic intake assistant** (use synthetic data only) | Structured extraction from free-text symptoms, strict scope limits, safety escalation | Booking or rescheduling appointments |
| **Lab notebook copilot** for a research group | Retrieval over protocols and past experiment logs with per-project permissions | Ordering reagents within budget |
| **Open-source maintainer triage bot** | Classifying issues, finding duplicates via hybrid search over thousands of issues, injection via issue text | Labelling, closing duplicates, requesting info |
| **Landlord-tenant helpdesk** | Policy and lease retrieval per building, multilingual users | Creating maintenance work orders, scheduling contractors |
| **Course TA agent** for a university class | Retrieval over lecture notes and forum, academic integrity guardrails | Extending deadlines within policy |
| **Personal finance inbox agent** | Extracting bills from emails (untrusted content), minimising data the model sees | Scheduling payments, with approval |
| **Field service copilot** for technicians | Manuals with diagrams and tables, offline-tolerant, latency on mobile | Ordering parts, closing jobs |
| **Procurement assistant** for a small company | Supplier catalogue search, quotes comparison, approval chains | Raising purchase orders above/below thresholds |

When choosing, check that your project has: a real user, data you can legally use (synthetic is fine), at least one action with real consequences, and a corpus that changes.

## Milestones

| When | Deliverable |
|---|---|
| Days 1 to 2 | One-page proposal: user, problem, success metrics, scope, data plan, risks |
| Days 3 to 5 | Design doc draft; first 40 eval cases; skeleton deployed |
| Days 6 to 9 | Core features; retrieval; guardrails; eval suite to 150 cases; judges calibrated |
| Days 10 to 11 | Observability, optimizations with before/after numbers; red-team pass |
| Day 12 | Design review with peers (use the review lesson's format) |
| Day 13 | Readiness review: checklist with evidence |
| Day 14 | Final presentation and live demo |

```viz
caption: Evidence work starts on day 3, not day 12. Eval cases grow alongside the features, and the last three days are reviews, not coding.
<div class="cells" style="--n:7"><i class="sk c">1</i><i class="sk c">2</i><i class="sk m">3</i><i class="sk m">4</i><i class="sk m">5</i><i class="sk c">6</i><i class="sk c">7</i><i class="sk c">8</i><i class="sk c">9</i><i class="sk m">10</i><i class="sk m">11</i><i class="sk g">12</i><i class="sk g">13</i><i class="sk g">14</i></div>
<div class="vz-row"><span class="ch sk c">build</span><span>proposal, features</span><span class="ch sk m">evidence</span><span>design doc, evals, numbers</span><span class="ch sk g">review</span><span>design, readiness, demo</span></div>
<p>evals run on days 3 to 11 too: 40 cases by day 5, 150 by day 9</p>
```

## The final presentation (15 minutes + 10 minutes questions)

1. **The problem and user** (1 min). Who, what, why it matters.
2. **Live demo** (4 min). One happy path, one edge case, one attack that fails, one approval flow. Show the trace for one request.
3. **Architecture** (3 min). One diagram, one request walk-through, two key ADRs with their "revisit when".
4. **Evidence** (4 min). Eval results by category with pass^k, judge calibration, red-team results, latency and cost per conversation with your optimization table, the dashboard.
5. **Failure modes and trade-offs** (2 min). What can still go wrong, how you would know, what you chose not to build.
6. **What's next** (1 min).

```viz
caption: Eight of the fifteen minutes are proof: the live demo and the evidence. Architecture gets three.
<div class="vz-bars"><span>problem, user</span><span class="bar sk"><i class="sk" style="--w:25%"></i></span><b>1 min</b><span>live demo</span><span class="bar sk"><i class="sk g" style="--w:100%"></i></span><b>4 min</b><span>architecture</span><span class="bar sk"><i class="sk" style="--w:75%"></i></span><b>3 min</b><span>evidence</span><span class="bar sk"><i class="sk g" style="--w:100%"></i></span><b>4 min</b><span>failure modes</span><span class="bar sk"><i class="sk" style="--w:50%"></i></span><b>2 min</b><span>what's next</span><span class="bar sk"><i class="sk" style="--w:25%"></i></span><b>1 min</b></div>
```

Practice the demo with network failure in mind: have a recorded backup.

## Grading rubric

Use this to self-assess or for peer review in a study group.

| Area | Excellent (4) | Adequate (2) | Missing (0) |
|---|---|---|---|
| Problem & design | Clear user and metrics; design doc with numbers, ADRs, threat model | Design doc present, some numbers | No design doc |
| Agent & tools | Tools well-designed, tiered, limits in code, approvals | Works, limits partly in prompt only | Unbounded tools |
| Retrieval | Hybrid + rerank, incremental, ACL in query, measured recall | Basic vector search, measured | Unmeasured |
| Evals | 150+ cases from real/synthetic/red-team sources, calibrated judges, CI gate, pass^k | Suite exists, partly automated | Ad hoc testing |
| Security | Trifecta analysis, red-team passes, isolation of untrusted content | Some mitigations, partial tests | None |
| Deployment | Auth, limits, pipeline, staging, rollback practiced | Deployed manually with auth | Local only |
| Observability | Traces across services/MCP, cost & quality dashboards, alerts + runbooks, kill switches tested | Traces and basic metrics | Logs only |
| Optimization | Before/after table with quality held | Some optimization, measured | None |
| Communication | Clear demo, honest trade-offs, crisp answers | Understandable | Unclear |

A total of 28+ out of 36 is a strong portfolio project.

## Make it count

- **Publish your repo** with the design doc, eval reports, and a short demo video. A well-documented capstone is a better signal to employers than a certificate.
- **Write it up**: a blog post on the hardest problem you solved, with numbers, helps others and gets you noticed.
- **Review someone else's**: running the design review questions on a peer's project is the best way to internalise them.

## Reference reading

- Every lesson's "design review questions": they are your checklist.
- [Production readiness](#w6-readiness) and [architecture review](#w6-review) lessons for templates.
- [What We Learned from a Year of Building with LLMs](https://applied-llms.org/).
- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) (Anthropic) and [A practical guide to building agents](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf) (OpenAI): two vendors' advice that agrees on starting simple.
- The [reading list](#resources) for provider docs, open-model serving, and other free courses.
