# Relay: reference implementation

Relay is the support agent for Northwind Outfitters (a fictional outdoor gear store) that students build in the
[AI System Design Course](../README.md). This folder is the working reference. Each lab has a git tag
(`lab1`, `lab2`, ...) so you can compare your code with a known-good version at every stage.

**Current stage: Lab 2** (scalable RAG), built on Lab 1:

- **Lab 1, agent service:** async FastAPI, streaming over server-sent events, tools with code-enforced limits,
  sessions in Postgres, a bounded agent loop, and background memory.
- **Lab 2, scalable RAG:** a 30-document knowledge base with access control, a Postgres job queue with retries
  and dead-lettering, hash-based incremental indexing, hybrid search with a reranker, output guardrails with one
  rewrite, and a retrieval eval.

## Layout

```
app/agent.py     the agent loop: parallel tools, timeouts, step limit, max_tokens/refusal handling, guardrail rewrite
app/tools.py     tools with identity scoping and refund rules enforced in code
app/ingest.py    parse, chunk with stable IDs, embed only changed chunks, job queue, reconcile (CLI: python -m app.ingest)
app/retrieval.py hybrid search (Postgres full text + pgvector), RRF, reranking; access control in the SQL
app/embeddings.py local embedding and reranking models (fastembed, CPU, no API key) and a hashing stand-in for tests
app/guardrails.py card redaction (Luhn), citation and refund-promise checks
app/llm.py       the model boundary (Anthropic SDK, prompt caching, refusal fallback); tests swap in a script
app/db.py        Postgres repository; every customer read is scoped in SQL
app/memory.py    background fact extraction from the customer's own words, with a poisoning filter
app/main.py      POST /chat (SSE), GET /sessions/{id}, GET /healthz
prompts/         the system prompt, versioned with the code
kb/              30 documents with front matter: title and acl (5 are internal, group:support only)
evals/           28 agent cases, the grader and runner, and the retrieval eval
tests/           46 tests that need no API key: embedded Postgres + a scripted model
```

## Run the tests (no API key, no Docker)

```bash
uv sync
uv run pytest
uv run python -m evals.run --validate
```

The tests start a throwaway Postgres 16 with pgvector through the `pgserver` package, give every test its own
schema, and replace the model with a script, so they are free and run offline.

## Run the API

```bash
docker compose up -d                 # Postgres with pgvector (or point RELAY_DATABASE_URL at any Postgres 16)
cp .env.example .env                 # add ANTHROPIC_API_KEY
uv run python -m scripts.seed_demo
uv run python -m app.ingest sync     # index kb/ (downloads ~150 MB of local models on first run)
uv run uvicorn app.main:app --reload
uv run python -m scripts.chat --customer c_77     # in another terminal
```

## Measure retrieval (free, local)

```bash
uv run python -m evals.retrieval --k 1
```

44 paraphrased queries against the 30-document knowledge base, using `bge-small-en-v1.5` embeddings and a
MiniLM cross-encoder, on a laptop CPU:

| Mode | recall@1 | MRR | recall@3 | p50 latency | Internal docs leaked to customers |
|---|---|---|---|---|---|
| Full text (OR query, `ts_rank_cd`) | 0.61 | 0.68 | 0.89 | <1 ms | 0 |
| Vector (pgvector HNSW) | 0.82 | 0.89 | 0.93 | 3 ms | 0 |
| Hybrid (RRF) | 0.77 | 0.84 | 0.93 | 3 ms | 0 |
| Hybrid + rerank | **0.89** | **0.96** | **0.97** | 82 ms | 0 |

Two lessons from these numbers. First, plain RRF hybrid scored *below* vector search alone at k=1 here, because
the weaker lexical ranker pulled noise into the top spot. Hybrid search is not automatically better: measure it on
your data. Second, the reranker gave the largest gain for about 80 ms. A 30-document corpus is small, so treat
these as a worked example of the method, not as general results.

## Run the evals (uses the API)

```bash
uv run python -m evals.run --trials 3 --save runs/main.json
```

Every case and trial runs in its own Postgres schema, so trials run concurrently and never see each other's
refunds. The runner prints per-case pass counts, pass^k, p95 latency, cost, and a must-never gate for
cross-customer and injection cases. With `RELAY_MODEL=claude-haiku-5-5`, a full 75-trial run costs well under a
dollar.

## Not in the reference yet

Authentication (Lab 4 replaces the `X-Customer-Id` and `X-Role` headers with JWTs), PDF parsing (Markdown only),
contextual chunk descriptions (needs an API key; see the Lab 2 page), judges and red-team generation (Lab 3),
tracing (Lab 5), and a job queue for memory extraction (Lab 4).
