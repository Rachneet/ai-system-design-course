---
id: drills
week: 99
kind: page
title: Design drills
short: Design drills
summary: Eight system design problems in interview format, each with a worked solution outline you can check your answer against.
---

## How to use these

Each drill is a 45-minute system design problem, the kind asked in AI engineering interviews and design reviews. Work through it before opening the outline:

1. **Clarify** (5 min): users, scale, latency, quality bar, risk. Write your assumptions.
2. **Estimate** (5 min): traffic, tokens, cost, storage.
3. **Design** (20 min): components, data flow, the agent or workflow, retrieval, evals, security.
4. **Deep dive** (10 min): the hardest part.
5. **Trade-offs and failure modes** (5 min).

```viz
caption: Ten minutes of framing buys twenty of design. Save the deep dive: it is where a strong answer shows depth instead of breadth.
<div class="vz-bars"><span>clarify</span><span class="bar sk"><i class="sk" style="--w:25%"></i></span><b>5 min</b><span>estimate</span><span class="bar sk"><i class="sk w" style="--w:25%"></i></span><b>5 min</b><span>design</span><span class="bar sk"><i class="sk c" style="--w:100%"></i></span><b>20 min</b><span>deep dive</span><span class="bar sk"><i class="sk c" style="--w:50%"></i></span><b>10 min</b><span>trade-offs</span><span class="bar sk"><i class="sk g" style="--w:25%"></i></span><b>5 min</b></div>
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk"><h5>Out of framing</h5><p>assumptions, users, risk, tokens and cost</p></div>
  <div class="vz-panel sk c"><h5>Out of design</h5><p>one diagram, one request walked end to end</p></div>
  <div class="vz-panel sk g"><h5>Out of trade-offs</h5><p>what you rejected, and when to revisit</p></div>
</div>
```

Every outline below is provider-neutral on purpose. Where it says "a small model" or "a large model", any tier works: a hosted API (OpenAI, Anthropic, Google Gemini, Mistral), an open-weights model on vLLM or Ollama, or a mix behind a gateway. Naming the deciding factor (quality on your evals, latency, price, data residency) scores better than naming a brand.

Then compare with the outline. The outlines are not the only right answer; they show the considerations a strong answer covers.

## Drill 1: Internal knowledge assistant for a 5,000-person company

*Employees ask questions over Confluence, Google Drive, and Slack. Answers must respect each employee's existing permissions. Target: answer in under 5 seconds, citations required.*

<details><summary>Solution outline</summary>

- **Clarify:** ~5,000 users, maybe 20,000 questions/day, peak ~3/sec. 2M documents, many updated daily. Permissions vary per document and change often. Wrong answers are tolerable if cited; leaks are not.
- **Estimate:** 2M docs × ~8 chunks = 16M chunks × 1,024 dims × 4 bytes ≈ 65 GB vectors (consider 512-dim or int8: ~16 GB).
- **Ingestion:** connectors per source using webhooks + nightly reconciliation; queue; parse, structure-aware chunking, contextual prefixes; incremental hash-based upserts. ACLs synced as document metadata, permission changes as fast-path events.
- **Access control:** the hardest part. Copying ACLs per chunk for Drive's sharing model is fragile; use coarse pre-filter (tenant, group membership snapshot) plus fine post-filter through a ReBAC service (OpenFGA-style) with over-fetching. Never cache answers across users.
- **Retrieval:** hybrid BM25 + vector, RRF, rerank top 50 → 8; query rewrite for follow-ups; source routing (Slack vs docs).
- **Generation:** cite chunk IDs; validate citations against retrieved set; abstain when nothing relevant.
- **Model hosting:** a hosted API is simplest. If documents may not leave the company, serve an open-weights model (Llama, Qwen, Mistral) with vLLM inside your network, and size the GPUs on measured goodput at the ~3 questions a second peak, not on a guess.
- **Evals:** retrieval recall@8 per source; permission leak tests (must-never); groundedness judge calibrated on 150 labels.
- **Failure modes:** stale permissions (revocation lag SLO), Slack noise, outdated docs outranking current ones (freshness boost), prompt injection in shared docs (assistant has no write tools; no external links rendered).

</details>

## Drill 2: Customer support agent that can issue refunds

*E-commerce, 50,000 conversations/day. The agent should resolve order status, returns, and refunds up to a limit. Fraud is a concern.*

<details><summary>Solution outline</summary>

- This is Relay. Key points: router to send simple intents to a small model; tool tiers with refund limits in code; identity from auth context only; approvals for high-value refunds as a state machine with idempotent execution; quarantined processing of emails and reviews.
- **Estimate:** 50k × ~7 calls × ~11k tokens → caching essential; compute cost per conversation for no-cache, cache, and routing designs.
- **Fraud:** per-customer refund velocity limits, anomaly alerts on refund rate, human review sampling, never let memory or content grant permissions.
- **Evals:** τ-bench-style end-state checks; must-not-call cases; red-team via reviews and emails; pass^k on refund flows.
- **Ops:** kill switch for `issue_refund`; cost and refund-rate alerts; canary on escalation and refund rates.

</details>

## Drill 3: Coding agent that opens pull requests from bug reports

*Given a GitHub issue, the agent reproduces the bug, writes a fix and a test, and opens a PR for human review. 500 issues/day across 200 repos.*

<details><summary>Solution outline</summary>

- **Execution environment:** per-task sandboxed containers with repo checkout, no production credentials, egress restricted to package registries.
- **Agent:** single agent with file read/write, search (grep), shell (in sandbox), test runner. Long context needs: just-in-time file exploration, compaction, notes file.
- **Durability:** tasks take 5 to 30 minutes; run in workers with checkpoints; budgets per task (tokens and wall time).
- **Security:** issue text is untrusted (injection could ask to exfiltrate secrets or add a backdoor). No secrets in sandbox; PRs always human-reviewed; diff scanners for suspicious changes (CI config, credentials, network calls).
- **Evals:** historical issues with known fixes (SWE-bench style): does the generated test fail before and pass after? Hidden tests. Measure resolve rate, PR acceptance rate in production.
- **Cost:** long agent runs; prompt caching on repo context; cap steps; route trivial issues (typos, docs) to cheaper path.

</details>

## Drill 4: Document processing pipeline for insurance claims

*Extract 40 fields from scanned claim forms and attachments (photos, invoices), validate, and route for approval. 100,000 documents/day, accuracy matters more than latency.*

<details><summary>Solution outline</summary>

- **Workflow, not agent:** the path is known. Steps: classify document type → OCR/vision extraction with structured output schema → code validation (dates, totals, policy number checksum) → cross-document consistency checks → confidence scoring → auto-approve, human review, or reject.
- **Batch:** use the provider's batch API for cost (OpenAI, Anthropic and Gemini all offer one), or run an open model offline at high batch size if you self-host; queue with priority lanes for urgent claims.
- **Human in the loop:** low-confidence fields highlighted in a review UI; corrections stored as labelled data.
- **Evals:** field-level precision/recall per document type on a labelled set; end-to-end decision accuracy; calibration of confidence scores (are 0.9-confidence fields right 90% of the time?).
- **Compliance:** PII handling, audit log of every decision with model version, explainability for denials, data residency.

</details>

## Drill 5: Multi-tenant RAG platform (B2B SaaS)

*Each customer company uploads its own documents and gets a chat assistant. 2,000 tenants, from 100 to 5M documents each.*

<details><summary>Solution outline</summary>

- **Isolation:** namespace per tenant (or RLS on shared tables for small tenants, dedicated indexes for large ones). Tenant ID from auth, enforced at the storage layer.
- **Noisy neighbours:** per-tenant ingestion queues and rate limits; per-tenant model token budgets; fair scheduling.
- **Sharding:** by tenant; large tenants get dedicated shards; small tenants packed.
- **Customisation:** per-tenant prompts and settings stored as versioned config; per-tenant eval sets for top customers.
- **Cost attribution:** tokens, storage, and compute per tenant; pricing tiers map to models and limits.
- **Failure modes:** cross-tenant cache hits, embedding model migration across 2,000 tenants (blue/green per tenant, gradual), one tenant's malicious documents attempting injection (no cross-tenant tools; outputs scoped).

</details>

## Drill 6: Research agent that writes reports from the web

*Users ask open-ended questions ("compare battery chemistries for grid storage"); the agent searches, reads, and writes a cited 2,000-word report in under 10 minutes.*

<details><summary>Solution outline</summary>

- **Multi-agent is justified:** orchestrator plans sub-questions; parallel sub-agents search and read (context isolation for large pages); orchestrator synthesises; a citation checker verifies each claim against sources.
- **Delegation quality:** explicit sub-task specs with output format and scope; effort scaling by question complexity.
- **Async UX:** job with progress events over SSE; resumable.
- **Security:** web content is untrusted; sub-agents have read-only tools; no private data in this flow, so the trifecta lacks private data (keep it that way: do not add user document access without isolation).
- **Evals:** rubric-based judges for coverage, accuracy, citation faithfulness; human expert review sample; cost and time per report.
- **Cost:** multi-agent uses many times the tokens of chat; cap sub-agents and searches per depth tier.

</details>

## Drill 7: Voice assistant for restaurant phone orders

*Takes orders by phone, answers menu questions, handles modifications. Must feel natural: under 800 ms response latency.*

<details><summary>Solution outline</summary>

- **Latency budget dominates:** streaming speech-to-text, a small fast model for dialogue, streaming text-to-speech, start speaking on first clause. Total budget: STT final ~200 ms + LLM TTFT ~300 ms + TTS first audio ~200 ms.
- **Structure:** order state as a structured object updated by tool calls (`add_item`, `modify_item`), not free text; confirm the order by reading it back.
- **Context:** menu in a cached prefix; keep conversation short.
- **Failure modes:** mishearing (confirmations, spelling-sensitive items), barge-in handling, allergies (hard rules: escalate or confirm; never guess), payment (never by voice to the model; hand to secure IVR or link).
- **Evals:** recorded call simulations with noise and accents; order accuracy (end-state), latency p95, handoff rate.

</details>

## Drill 8: Add memory to an existing chat assistant with 10M users

*Users want the assistant to remember preferences and past context. Privacy and correctness are critical.*

<details><summary>Solution outline</summary>

- **Write path:** background extraction after sessions, small model, structured atomic facts with confidence and source; consolidation (add, update, skip) against existing memories; never store instructions or sensitive categories without consent.
- **Read path:** profile summary always injected (small), plus semantic retrieval of relevant memories filtered by user ID; memory labelled as possibly outdated.
- **Scale:** 10M users × ~50 memories × 1 KB ≈ 500 GB text + vectors; shard by user ID; most users inactive, so tiered storage.
- **User control:** view, edit, delete memories; "forget this" commands; full deletion on account removal including vectors, caches, traces.
- **Evals:** extraction precision (wrong memories are worse than none), personalization benefit via A/B on satisfaction, memory poisoning red-team.
- **Failure modes:** stale facts, cross-user leakage (filter enforced at storage layer), creepiness (surfacing remembered facts unexpectedly).

</details>
