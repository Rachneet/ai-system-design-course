---
id: w6-review
week: 6
kind: lesson
title: Reviewing architecture and design choices
short: Architecture review
minutes: 40
summary: How to write a design document for an AI system, record decisions so they can be revisited, and run a design review that finds the problems before production does.
---

## Why write it down

By Week 6, Relay has a dozen components and a hundred decisions behind them. Some were deliberate; some were whatever worked at 1 a.m. A design review makes them visible, so you can defend the good ones and fix the accidental ones. It is also the format for a system design interview and for most promotion cases in engineering.

## The design document

A good AI system design doc is 5 to 10 pages. Template:

1. **Problem and users.** Who uses it, for what, and what "good" looks like in their terms. Include non-goals.
2. **Requirements.**
   - Functional: what it does.
   - Quality: target pass rates per category on your eval suite.
   - Latency: TTFT and turn p95.
   - Scale: conversations per day, peak per second, corpus size, growth.
   - Cost: target cost per conversation and monthly ceiling.
   - Security and compliance: data classes handled, residency, retention, audit.
3. **Architecture.** One diagram showing components, data stores, trust boundaries, and external dependencies. Then a request walk-through: a real user request traced through every component.
4. **Key design decisions.** For each: options considered, the choice, why, and what would make you revisit it.
5. **Agent design.** Workflow vs agent and why; tool list with tiers; context budget; memory design; model choices per role.
6. **Data and retrieval.** Sources, ingestion, freshness, chunking, retrieval pipeline, access control.
7. **Evaluation.** Dataset sources and size, graders, judge calibration, gates, online evaluation.
8. **Security.** Threat model (lethal trifecta per workflow), mitigations, red-team results.
9. **Operations.** Deployment, SLOs, dashboards, alerts, kill switches, runbooks, on-call.
10. **Cost model.** Per-conversation breakdown and monthly projection at 1x and 10x.
11. **Risks and open questions.**

> [!rule] Every number in the design doc should come from a measurement or a calculation shown in the doc. "Fast" and "cheap" are not requirements.

## Architecture decision records

Decisions get forgotten and re-argued. An **ADR** is a one-page record of a single decision, kept in the repo (`docs/adr/0007-postgres-for-vectors.md`). See [adr.github.io](https://adr.github.io/) for templates.

```markdown
# ADR 0007: Use Postgres + pgvector for retrieval

Status: accepted (2026-10-02)

## Context
Corpus: 40k chunks, growing ~2k/month. Need ACL filters joined to documents, hybrid search,
transactional updates with document metadata. Team of 3, no dedicated ops.

## Options
1. Postgres + pgvector + tsvector (already run Postgres)
2. Managed vector DB + separate keyword search
3. Elasticsearch/OpenSearch with dense vectors

## Decision
Option 1. One system, transactional ACL updates, hybrid in one SQL query.
Measured: recall@6 0.91 (hybrid + rerank), p95 retrieval 64 ms at 40k chunks.

## Consequences
+ No new infrastructure; RLS for tenant isolation.
- HNSW memory grows with corpus; revisit at ~5M chunks or if p95 > 150 ms.
- Full-text ranking is weaker than BM25; revisit if lexical recall drops (ParadeDB is an option).
```

The "revisit when" line is the most valuable part: it turns a decision into a monitored assumption.

## Running the review

Invite two or three reviewers, ideally including someone who did not build it. Send the doc a day ahead. In the meeting:

1. **Author walks a request end to end** (10 minutes), not a slide tour of components.
2. **Reviewers ask questions by area.** Use the design review questions from each lesson in this course as the checklist. They were written for exactly this.
3. **Record findings** with severity: blocker (must fix before launch), major (fix soon), minor, question.
4. **Close with decisions**: what changes, who owns it, by when.

### The questions that find the most problems

- *"What happens when this dependency is slow or down?"* Ask it of every arrow in the diagram.
- *"Where does this value come from, and can the user or the model influence it?"* Ask it of every identity, permission, and amount.
- *"How do you know?"* Ask it of every claim about quality, cost, and latency.
- *"What happens at 10x?"* Ask it of every store, queue, and rate limit.
- *"What is the worst thing the agent can do with these tools if fully compromised?"*
- *"Which decision here would be most expensive to reverse?"*

## Common findings in AI system reviews

Patterns that come up again and again:

| Finding | Typical fix |
|---|---|
| Business limits only in the prompt | Enforce in tool code; prompt explains them |
| Identity passed through model arguments | Take identity from the auth context in every tool |
| No must-not-call or end-state evals | Add state checks and forbidden-action cases |
| Judges never calibrated | Label 100 examples, measure kappa |
| No cost per conversation metric | Instrument usage and price table |
| Cache hit rate unknown, prompt has a timestamp at the top | Stable prefix, measure hit rate |
| Single model, no fallback, no circuit breaker | Tested fallback path, breaker, degradation plan |
| Retrieval ACL filter applied after LLM call or in the prompt | Filter in SQL before generation |
| Long tasks run inside HTTP requests | Jobs + workers + checkpoints |
| Traces contain raw PII indefinitely | Redaction processor, retention policy, access control |

## Presenting trade-offs

Reviewers trust you more when you show what you gave up. For each major decision, a short trade-off table:

| | Single agent, Sonnet, all tools | Router + Haiku for simple intents |
|---|---|---|
| Eval pass rate (PR suite) | 93.1% | 92.8% |
| Cost / conversation p50 | $0.017 | $0.008 |
| TTFT p95 | 2.1 s | 1.4 s |
| Complexity | Lower | Router + two prompts to maintain |
| Decision | | **Chosen**: 2x cheaper, quality equal within noise; router errors monitored |

## Design review questions

> [!interview] Which decision in this system would be most expensive to reverse, and why are you confident in it?

> [!interview] Show me the "revisit when" conditions for your ADRs. Are any already true?

> [!interview] What did your reviewers find that you had missed?

## Further reading

- [Architecture Decision Records](https://adr.github.io/), templates and background.
- [System Design Primer](https://github.com/donnemartin/system-design-primer), classic distributed systems foundations.
- [Building A Generative AI Platform](https://huyenchip.com/2024/07/25/genai-platform.html), Chip Huyen, a reference architecture to compare yours against.
- [Emerging Patterns in Building GenAI Products](https://martinfowler.com/articles/gen-ai-patterns/), martinfowler.com.
- [AWS Well-Architected Generative AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/generative-ai-lens.html), a structured question list.

```quiz
[
  {"q": "What is the most valuable line in an ADR?", "options": ["The date", "The conditions under which you would revisit the decision", "The author", "The status"], "answer": 1, "why": "It turns a decision into a monitored assumption, so you know when it has expired."},
  {"q": "How should an author start a design review?", "options": ["A tour of each component", "Walking one real request end to end through the system", "Showing the eval dashboard", "Listing technologies used"], "answer": 1, "why": "Following a request exposes interfaces, trust boundaries, and failure handling that a component tour hides."},
  {"q": "A design doc says retrieval is \"fast\". What should a reviewer ask for?", "options": ["Nothing", "A measured p95 at a stated corpus size and load", "The vendor's marketing page", "A different database"], "answer": 1, "why": "Requirements and claims need numbers with conditions, from measurements in the doc."}
]
```
