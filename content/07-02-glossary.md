---
id: glossary
week: 7
kind: page
title: Glossary
short: Glossary
summary: Short, plain definitions of the terms used throughout the course, from ADR to τ-bench.
---

| Term | Meaning |
|---|---|
| **ADR** | Architecture decision record. A one-page note of one decision: context, options, choice, consequences, and when to revisit. |
| **Agent** | A loop in which a model chooses actions (tool calls) based on what it observes, until it decides the task is done. |
| **ANN** | Approximate nearest neighbour search. Finds vectors close to a query fast, trading a little accuracy. HNSW and IVF are common index types. |
| **At-least-once delivery** | A queue guarantee that every message is delivered, possibly more than once. Requires idempotent handlers. |
| **BM25** | A classic keyword ranking function based on term frequency and rarity. Strong on exact terms and identifiers. |
| **Burn rate** | How fast you are consuming your error budget relative to the sustainable rate. Used for SLO alerting. |
| **Circuit breaker** | A wrapper that stops calling a failing dependency for a cool-down period and uses a fallback instead. |
| **Cohen's kappa** | Agreement between two raters corrected for chance agreement. Used to compare a judge with human labels. |
| **Compaction** | Summarising older conversation turns to keep the context within budget. |
| **Context engineering** | Deciding what tokens go into each model call, in what order and form: instructions, tools, memory, retrieved data, history. |
| **Contextual retrieval** | Adding a short, model-generated description of where a chunk sits in its document before embedding and indexing it. |
| **Cross-encoder (reranker)** | A model that reads a query and a document together to score relevance. Accurate, too slow for first-stage search. |
| **Dead-letter queue (DLQ)** | Where jobs go after exhausting retries, so they do not block the queue and can be inspected. |
| **Dual LLM pattern** | Separating a privileged model with tools from a quarantined model that reads untrusted content, so injected text cannot trigger actions. |
| **Embedding** | A vector representation of text where similar meanings are close together. |
| **Error analysis** | Reading traces, noting the first failure in each, and grouping failures into categories to prioritise work and evals. |
| **Error budget** | The amount of unreliability an SLO allows over a period (for example 0.5% of requests in 30 days). |
| **Golden signals** | Latency, traffic, errors, saturation: the core service health metrics. |
| **Groundedness** | Whether an answer's claims are supported by the provided sources. |
| **Guardrail** | A check outside the main model call that can block, modify, or flag inputs, outputs, or tool calls. |
| **HNSW** | Hierarchical Navigable Small World graph. The most common ANN index; fast and accurate, memory-hungry. |
| **HyDE** | Hypothetical Document Embeddings. Embed a generated hypothetical answer instead of the question to improve retrieval. |
| **Hybrid search** | Combining lexical (BM25) and vector search, usually with rank fusion. |
| **Idempotency key** | A client-supplied unique key that lets a server recognise and safely deduplicate retried requests. |
| **Indirect prompt injection** | Malicious instructions embedded in content the agent processes (web pages, emails, documents, tool results). |
| **Lethal trifecta** | Private data access + untrusted content + external communication. Together they enable data exfiltration via injection. |
| **LLM-as-judge** | Using a model to grade outputs against criteria. Must be calibrated against human labels. |
| **Little's law** | Concurrency = arrival rate × time in system. Used to size instances. |
| **MCP** | Model Context Protocol. An open protocol for connecting models and agents to tools and data sources through servers. |
| **McNemar's test** | A statistical test on paired pass/fail results, used to decide if a version regressed on the same cases. |
| **Memory poisoning** | Getting false facts or instructions stored in an agent's long-term memory so they affect future sessions. |
| **MRR** | Mean reciprocal rank. The average of 1/rank of the first relevant result. |
| **nDCG** | Normalised discounted cumulative gain. A rank-aware relevance metric supporting graded relevance. |
| **OpenTelemetry (OTel)** | The vendor-neutral standard for traces, metrics, and logs, with semantic conventions for GenAI. |
| **Outbox pattern** | Writing an event to an outbox table in the same transaction as the data change, then publishing it, to avoid dual-write inconsistency. |
| **pass@k / pass^k** | Passed at least once in k trials (capability) / passed in all k trials (reliability). |
| **pgvector** | A Postgres extension for vector storage and similarity search. |
| **Prompt caching** | Provider-side reuse of a processed prompt prefix, giving cheaper and faster input tokens on repeats. |
| **Prompt injection** | Input that causes a model to follow an attacker's instructions instead of the developer's. |
| **RAG** | Retrieval-augmented generation. Retrieving relevant data and putting it in the prompt so the model can use it. |
| **Recall@k** | The fraction of relevant items that appear in the top k results. |
| **RLS** | Row-level security. Database policies that restrict which rows a session can see, enforcing tenant isolation. |
| **RRF** | Reciprocal rank fusion. Combines ranked lists by summing 1/(k + rank). |
| **Semantic cache** | A cache that returns a stored answer for a sufficiently similar question. Risky for personalised or permissioned content. |
| **Shadow mode** | Running a new version on copies of live traffic without showing or acting on its output, to compare with the current version. |
| **SLI / SLO** | Service level indicator (what you measure) / objective (the target). |
| **Span / trace** | A span is one timed unit of work; a trace is the tree of spans for one request. |
| **SSE** | Server-sent events. A simple HTTP streaming format for sending tokens to a browser. |
| **Tail sampling** | Deciding which traces to keep after they complete, so you can keep all errors and outliers. |
| **TTFT** | Time to first token. How long until the user sees output begin. |
| **Tool calling** | The model requests a function call with structured arguments; your code executes it and returns the result. |
| **Workflow** | A fixed path of LLM calls and code, where your code decides the order of steps. |
| **τ-bench** | A benchmark for tool-using agents in customer-service domains, with simulated users and database-state grading. |
