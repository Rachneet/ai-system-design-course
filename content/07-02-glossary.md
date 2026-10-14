---
id: glossary
week: 7
kind: page
title: Glossary
short: Glossary
summary: Short, plain definitions of the terms used throughout the course, from ADR and goodput to KV cache and τ-bench.
---

| Term | Meaning |
|---|---|
| **A2A** | Agent2Agent protocol. An open protocol, now at the Linux Foundation, for one agent to discover and delegate to another agent built by a different team or vendor. MCP connects agents to tools; A2A connects agents to agents. |
| **ADR** | Architecture decision record. A one-page note of one decision: context, options, choice, consequences, and when to revisit. |
| **Agent** | A loop in which a model chooses actions (tool calls) based on what it observes, until it decides the task is done. |
| **ANN** | Approximate nearest neighbour search. Finds vectors close to a query fast, trading a little accuracy. HNSW and IVF are common index types. |
| **At-least-once delivery** | A queue guarantee that every message is delivered, possibly more than once. Requires idempotent handlers. |
| **BM25** | A classic keyword ranking function based on term frequency and rarity. Strong on exact terms and identifiers. |
| **Burn rate** | How fast you are consuming your error budget relative to the sustainable rate. Used for SLO alerting. |
| **Chunked prefill** | Splitting a long prompt's prefill into pieces of a few thousand tokens and running each piece alongside other users' decode steps, so one long prompt does not freeze everyone's stream. |
| **Circuit breaker** | A wrapper that stops calling a failing dependency for a cool-down period and uses a fallback instead. |
| **Cohen's kappa** | Agreement between two raters corrected for chance agreement. Used to compare a judge with human labels. |
| **Compaction** | Summarising older conversation turns to keep the context within budget. |
| **Context engineering** | Deciding what tokens go into each model call, in what order and form: instructions, tools, memory, retrieved data, history. |
| **Contextual retrieval** | Adding a short, model-generated description of where a chunk sits in its document before embedding and indexing it. |
| **Continuous batching** | Scheduling at the level of each decode step, so a new request takes a slot the moment another finishes instead of waiting for the whole batch. Introduced as iteration-level scheduling in Orca; every modern serving engine does it. |
| **Cross-encoder (reranker)** | A model that reads a query and a document together to score relevance. Accurate, too slow for first-stage search. |
| **Dead-letter queue (DLQ)** | Where jobs go after exhausting retries, so they do not block the queue and can be inspected. |
| **Decode** | The second phase of generation: writing the reply one token at a time, running the whole model once per token. Limited mainly by memory bandwidth; sets TPOT. |
| **Disaggregated serving** | Running prefill and decode on separate GPU pools, shipping the KV cache between them, so each pool is sized and tuned for its own bottleneck. |
| **Dual LLM pattern** | Separating a privileged model with tools from a quarantined model that reads untrusted content, so injected text cannot trigger actions. |
| **Embedding** | A vector representation of text where similar meanings are close together. |
| **Error analysis** | Reading traces, noting the first failure in each, and grouping failures into categories to prioritise work and evals. |
| **Error budget** | The amount of unreliability an SLO allows over a period (for example 0.5% of requests in 30 days). |
| **Expert parallelism** | Spreading the experts of an MoE model across GPUs, with the network routing each token to the GPUs that hold its chosen experts. |
| **FP8** | An 8-bit floating-point number format. Halves weight memory against 16-bit and is natively supported on NVIDIA Hopper (H100, H200); the usual safe default for quantized serving there. |
| **Golden signals** | Latency, traffic, errors, saturation: the core service health metrics. |
| **Goodput** | The highest request rate a system can serve while meeting its latency targets (TTFT and TPOT). Counts only work that arrived in time, unlike raw throughput. |
| **Groundedness** | Whether an answer's claims are supported by the provided sources. |
| **Guardrail** | A check outside the main model call that can block, modify, or flag inputs, outputs, or tool calls. |
| **HNSW** | Hierarchical Navigable Small World graph. The most common ANN index; fast and accurate, memory-hungry. |
| **Hybrid search** | Combining lexical (BM25) and vector search, usually with rank fusion. |
| **HyDE** | Hypothetical Document Embeddings. Embed a generated hypothetical answer instead of the question to improve retrieval. |
| **Idempotency key** | A client-supplied unique key that lets a server recognise and safely deduplicate retried requests. |
| **Indirect prompt injection** | Malicious instructions embedded in content the agent processes (web pages, emails, documents, tool results). |
| **KV cache** | The keys and values of every earlier token, kept in GPU memory so each new token does not recompute them. Grows with every token of every live conversation; usually the largest use of memory under load. |
| **Lethal trifecta** | Private data access + untrusted content + external communication. Together they enable data exfiltration via injection. |
| **Little's law** | Concurrency = arrival rate × time in system. Used to size instances. |
| **LLM-as-judge** | Using a model to grade outputs against criteria. Must be calibrated against human labels. |
| **McNemar's test** | A statistical test on paired pass/fail results, used to decide if a version regressed on the same cases. |
| **MCP** | Model Context Protocol. An open protocol for connecting models and agents to tools and data sources through servers. |
| **Memory poisoning** | Getting false facts or instructions stored in an agent's long-term memory so they affect future sessions. |
| **Model gateway** | A proxy between your application and model providers (LiteLLM, OpenRouter, Hugging Face Inference Providers, or your own) that gives one API, one set of keys, fallbacks, budgets, and logging across hosted and self-hosted models. |
| **Model spec** | A published document in which a model developer states how its models should behave, including whose instructions win when system, developer and user disagree. OpenAI's Model Spec calls this the chain of command. |
| **MoE** | Mixture of experts. A model with many expert sub-networks per layer, of which a router activates only a few per token. Memory follows total parameters; compute per token follows active parameters. |
| **MRR** | Mean reciprocal rank. The average of 1/rank of the first relevant result. |
| **nDCG** | Normalised discounted cumulative gain. A rank-aware relevance metric supporting graded relevance. |
| **NVFP4** | NVIDIA's 4-bit floating-point format for Blackwell GPUs: 4-bit values in blocks of 16, each block with its own FP8 scale, about 4.5 bits per value in total. |
| **OpenAI-compatible API** | The chat completions request and response format that OpenAI introduced and many others accept: Gemini, vLLM, SGLang, Ollama, OpenRouter, LiteLLM and Hugging Face Inference Providers. Switching provider is often a change of base URL, key and model name, but features such as caching and tool-call details still differ. |
| **OpenTelemetry (OTel)** | The vendor-neutral standard for traces, metrics, and logs, with semantic conventions for GenAI. |
| **Outbox pattern** | Writing an event to an outbox table in the same transaction as the data change, then publishing it, to avoid dual-write inconsistency. |
| **PagedAttention** | The vLLM technique of storing the KV cache in small fixed-size blocks allocated as tokens arrive, like virtual memory pages, which cuts wasted cache memory to a few percent. |
| **pass@k / pass^k** | Passed at least once in k trials (capability) / passed in all k trials (reliability). |
| **pgvector** | A Postgres extension for vector storage and similarity search. |
| **Prefill** | The first phase of generation: reading the whole prompt in one parallel pass and building its KV cache. Compute-bound; sets most of TTFT. |
| **Prompt caching** | Provider-side reuse of a processed prompt prefix, giving cheaper and faster input tokens on repeats. |
| **Prompt injection** | Input that causes a model to follow an attacker's instructions instead of the developer's. |
| **Quantization** | Storing model weights (and sometimes the KV cache) in fewer bits, such as FP8, INT4 or NVFP4 instead of 16-bit, for faster decode and more memory headroom. Check quality on your own evals. |
| **RAG** | Retrieval-augmented generation. Retrieving relevant data and putting it in the prompt so the model can use it. |
| **Recall@k** | The fraction of relevant items that appear in the top k results. |
| **RLS** | Row-level security. Database policies that restrict which rows a session can see, enforcing tenant isolation. |
| **RRF** | Reciprocal rank fusion. Combines ranked lists by summing 1/(k + rank). |
| **Semantic cache** | A cache that returns a stored answer for a sufficiently similar question. Risky for personalised or permissioned content. |
| **Shadow mode** | Running a new version on copies of live traffic without showing or acting on its output, to compare with the current version. |
| **SLI / SLO** | Service level indicator (what you measure) / objective (the target). |
| **Span / trace** | A span is one timed unit of work; a trace is the tree of spans for one request. |
| **Speculative decoding** | A small draft model (or extra heads) guesses several tokens and the large model verifies them in one pass. Same output distribution, fewer passes; helps most when the GPU is not already busy. |
| **SSE** | Server-sent events. A simple HTTP streaming format for sending tokens to a browser. |
| **Tail sampling** | Deciding which traces to keep after they complete, so you can keep all errors and outliers. |
| **Tensor / pipeline parallelism** | Two ways to split a model too big for one GPU. Tensor parallelism slices every layer across GPUs that talk constantly, so it stays inside one fast node; pipeline parallelism gives each GPU a block of layers and can span nodes. |
| **Tool calling** | The model requests a function call with structured arguments; your code executes it and returns the result. |
| **TPOT** | Time per output token, also called inter-token latency. The steady gap between streamed tokens during decode. |
| **TTFT** | Time to first token. How long until the user sees output begin. |
| **Workflow** | A fixed path of LLM calls and code, where your code decides the order of steps. |
| **τ-bench** | A benchmark for tool-using agents in customer-service domains, with simulated users and database-state grading. |
