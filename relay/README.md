# Relay: reference implementation

Relay is the support agent for Northwind Outfitters (a fictional outdoor gear store) that students build in the
[AI System Design Course](../README.md). This folder is the working reference. Each lab has a git tag
(`lab1`, `lab2`, ...) so you can compare your code with a known-good version at every stage.

**Current stage: Lab 1** (agent service): async FastAPI, streaming over server-sent events, tools with
code-enforced limits, sessions in Postgres, a bounded agent loop, background memory, and a 25-case eval suite.

## Layout

```
app/agent.py     the agent loop: tools in parallel, timeouts, step limit, max_tokens/refusal handling
app/tools.py     tools with identity scoping and refund rules enforced in code
app/llm.py       the model boundary (Anthropic SDK, prompt caching, refusal fallback); tests swap in a script
app/db.py        Postgres repository; every customer read is scoped in SQL
app/memory.py    background fact extraction from the customer's own words, with a poisoning filter
app/main.py      POST /chat (SSE), GET /sessions/{id}, GET /healthz
prompts/         the system prompt, versioned with the code
kb/              policy documents searched by search_kb (Lab 2 replaces this with hybrid retrieval)
evals/           25 cases, the grader, and the runner
tests/           29 tests that need no API key: embedded Postgres + a scripted model
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
uv run uvicorn app.main:app --reload
uv run python -m scripts.chat --customer c_77     # in another terminal
```

## Run the evals (uses the API)

```bash
uv run python -m evals.run --trials 3 --save runs/main.json
```

Every case and trial runs in its own Postgres schema, so trials run concurrently and never see each other's
refunds. The runner prints per-case pass counts, pass^k, p95 latency, cost, and a must-never gate for
cross-customer and injection cases. With `RELAY_MODEL=claude-haiku-5-5`, a full 75-trial run costs well under a
dollar.

## What Lab 1 deliberately leaves out

Authentication (Lab 4 replaces the `X-Customer-Id` header with JWTs), retrieval beyond keyword matching
(Lab 2), judges and red-team generation (Lab 3), tracing (Lab 5), and a job queue for memory extraction (Lab 4).
