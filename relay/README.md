# Relay: reference implementation

Relay is the support agent for Northwind Outfitters (a fictional outdoor gear store) that students build in the
[AI System Design Course](../README.md). This folder is the working reference. Each lab has a git tag
(`lab1`, `lab2`, ...) so you can compare your code with a known-good version at every stage.

**Current stage: Lab 4** (secure API and deployment), built on Labs 1 to 3:

- **Lab 1, agent service:** async FastAPI, streaming over server-sent events, tools with code-enforced limits,
  sessions in Postgres, a bounded agent loop, and background memory.
- **Lab 2, scalable RAG:** a 30-document knowledge base with access control, a Postgres job queue with retries
  and dead-lettering, hash-based incremental indexing, hybrid search with a reranker, output guardrails with one
  rewrite, and a retrieval eval.
- **Lab 3, evals and security:** 163 eval cases from four sources (hand-written, dimension-generated, red-team,
  and encoded attack variants) in dev and held-out splits, scripted and simulated multi-turn conversations, two
  binary LLM judges with calibration tooling, a merge gate with an exact McNemar test against a baseline,
  error-analysis tooling, and hardened tools: tool tiers per channel, quarantined handling of reviews and emails,
  and link sanitising.
- **Lab 4, secure API and deployment:** JWT verification against an identity provider's JWKS (with a dev signing
  mode for local work), per-customer rate limits and daily token budgets in Postgres, a refund-approval state
  machine with Idempotency-Key replay, a worker process with an outbox-style job queue (memory extraction now
  waits until a session is quiet), readiness checks, a non-root container image, a CI job that runs the real
  containers, and a Cloud Run pipeline with staging, a 10% canary, and one-command rollback.

## Layout

```
app/agent.py     the agent loop: parallel tools, timeouts, step limit, max_tokens/refusal handling, guardrail rewrite
app/tools.py     tools with identity scoping and refund rules enforced in code
app/ingest.py    parse, chunk with stable IDs, embed only changed chunks, job queue, reconcile (CLI: python -m app.ingest)
app/retrieval.py hybrid search (Postgres full text + pgvector), RRF, reranking; access control in the SQL
app/embeddings.py local embedding and reranking models (fastembed, CPU, no API key) and a hashing stand-in for tests
app/guardrails.py card redaction (Luhn), citation and refund-promise checks, link and image sanitising
app/quarantine.py tool-less model calls that turn reviews and emails into narrow structured fields
app/channels.py   the email channel: assist mode, no direct refunds
app/auth.py       bearer-token verification; identity and staff role come only from the token
app/limits.py     token-bucket rate limits and daily token budgets
app/approvals.py  approval state machine and Idempotency-Key handling
app/jobs.py       job queue with debouncing and retries;  app/worker.py runs it (python -m app.worker)
Dockerfile        multi-stage uv build, non-root, one image for API and worker
infra/            one-time Google Cloud setup (.github/workflows/deploy.yml does the rest)
app/llm.py       the model boundary (Anthropic SDK, prompt caching, refusal fallback); tests swap in a script
app/db.py        Postgres repository; every customer read is scoped in SQL
app/memory.py    background fact extraction from the customer's own words, with a poisoning filter
app/main.py      POST /chat (SSE), GET /sessions/{id}, GET /healthz
prompts/         the system prompt, versioned with the code
kb/              30 documents with front matter: title and acl (5 are internal, group:support only)
evals/cases/     dev/ and heldout/ case files; generated ones come from evals/generate.py
evals/           runner, grader, gates.yaml, judges (+ calibration data), simulator, error analysis, retrieval eval
tests/           76 tests that need no API key: embedded Postgres + a scripted model
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
cp .env.example .env                 # add ANTHROPIC_API_KEY and a random RELAY_DEV_JWT_SECRET
uv run python -m app.migrate
uv run python -m scripts.seed_demo
uv run python -m app.worker &        # indexes kb/ (downloads ~150 MB of local models on first run), runs jobs
uv run uvicorn app.main:app --reload
uv run python -m scripts.chat --customer c_77     # in another terminal; mints a dev token
```

Staff endpoints (`GET /approvals`, `POST /approvals/{id}/decision`) need a token with the staff role:
`uv run python -m scripts.dev_token s_1 --staff`.

## Deploy

CI builds the image and runs it on every push: migration, API and worker containers, an authenticated two-turn
chat, knowledge-base indexing by the worker, and a graceful shutdown. The image is 417 MB, most of it the local
embedding and reranking runtime (ONNX). A deployment that calls a hosted embedding API instead could drop that.

`.github/workflows/deploy.yml` deploys to Cloud Run once you run `infra/setup_gcp.sh` and set four repository
variables. **It has not been run against a real Google Cloud project**; expect to adjust names and flags on your
first deploy. Rollback is one command:
`gcloud run services update-traffic relay-api --to-revisions=PREVIOUS_REVISION=100`.

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

| Suite | Cases | Default trials | Use |
|---|---|---|---|
| `smoke` | 10 must-pass cases | 1 | every push |
| `pr` | 145 dev cases | 3 | the merge gate |
| `release` | 163 (dev + held-out) | 5 | before a release |

```bash
uv run python -m evals.run --suite smoke
uv run python -m evals.run --suite pr --save runs/main.json         # on main
uv run python -m evals.run --suite pr --baseline runs/main.json     # on your branch: flags significant regressions
uv run python -m evals.calibrate                                    # judge agreement with labels (fail recall, kappa)
uv run python -m evals.error_analysis worksheet runs/main.json      # then read, note, and tally
```

The gate (`evals/gates.yaml`) blocks on any must-never failure (cross-customer access, obeyed injections,
exfiltration), per-category pass-rate floors, latency and cost budgets, and a significant regression against a
baseline run. In CI, the `evals` job runs the PR suite when the repository has an `EVAL_ANTHROPIC_API_KEY` secret.

**What is constructed rather than real.** The judge calibration sets (`evals/judges/*.jsonl`) are built from
templates with labels fixed by construction (`"labelled_by": "constructed"`). They check that each judge
works on clear and borderline wording. Before trusting a judge on your traffic, a domain expert must label real
transcripts and add them to the same files. Likewise, `evals/analysis/` is empty until you run error analysis on
real conversations.

**Cost estimate (not yet measured).** The PR suite is 145 cases × 3 trials = 435 agent runs. With
`RELAY_MODEL=claude-haiku-5-5` and mostly cached prompts, that is roughly $1 of agent calls, plus about $3 for the
roughly 180 judge calls on Opus 5.5. Pass `--no-judges` while iterating, and replace this estimate with the
cost the runner prints after your first real run.

## Not in the reference yet

PDF parsing (Markdown only),
contextual chunk descriptions (needs an API key; see the Lab 2 page), model-generated red-team paraphrases,
tracing, cost dashboards, alerts, and online judging of production traffic (Lab 5).
