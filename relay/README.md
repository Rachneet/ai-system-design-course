# Relay: reference implementation

Relay is the support agent for Northwind Outfitters (a fictional outdoor gear store) that students build in the
[AI System Design Course](../README.md). This folder is the working reference. Each lab has a git tag
(`lab1`, `lab2`, ...) so you can compare your code with a known-good version at every stage.

**Current stage: Lab 5** (observability, scaling and optimization), built on Labs 1 to 4:

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
- **Lab 5, observability and optimization:** OpenTelemetry traces following the GenAI conventions (one trace per
  turn; content recording is opt-in and redacted), Prometheus metrics, a carrier MCP server whose spans join
  Relay's trace through `params._meta`, retries with full jitter, a circuit breaker and fallback model, fault
  injection for game days, kill switches (`/flags`), an optional small-model router, feedback and online judging
  with a review queue, alert rules with runbooks, a tail-sampling Collector config, and a Grafana dashboard.

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
app/telemetry.py  tracing setup, redaction, trace links for jobs;  app/metrics.py  Prometheus metrics
app/resilience.py retries, circuit breaker, fallback, fault injection;  app/flags.py  kill switches
app/router.py     optional small-model routing;  app/online.py  online judging and the review queue
mcp_servers/      the carrier tracking MCP server (python -m mcp_servers.shipping)
ops/              alert rules, runbooks, Collector config, Grafana dashboard, local observability stack
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
tests/           92 tests that need no API key: embedded Postgres + a scripted model
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
cp .env.example .env                 # add a provider key (see below) and a random RELAY_DEV_JWT_SECRET
uv run python -m app.migrate
uv run python -m scripts.seed_demo
uv run python -m app.worker &        # indexes kb/ (downloads ~150 MB of local models on first run), runs jobs
uv run uvicorn app.main:app --reload
uv run python -m scripts.chat --customer c_77     # in another terminal; mints a dev token
```

Staff endpoints (`GET /approvals`, `POST /approvals/{id}/decision`) need a token with the staff role:
`uv run python -m scripts.dev_token s_1 --staff`.

## Choose any model provider

Every model setting takes a spec, `provider:model`, so you can run Relay on any provider and mix them. For example,
the agent on one vendor, the fallback on another, and the judge on a third family so it does not grade its own habits.

| Provider | Example spec | Key variable |
|---|---|---|
| Anthropic (native: prompt caching, refusal fallback) | `anthropic:claude-haiku-5-5` | `ANTHROPIC_API_KEY` |
| OpenAI | `openai:gpt-5` | `OPENAI_API_KEY` |
| Google Gemini (OpenAI-compatible endpoint) | `gemini:gemini-2.5-flash` | `GEMINI_API_KEY` |
| OpenRouter (hundreds of models, one key) | `openrouter:qwen/qwen3-235b-a22b` | `OPENROUTER_API_KEY` |
| Hugging Face Inference Providers | `huggingface:meta-llama/Llama-3.3-70B-Instruct` | `HF_TOKEN` |
| Ollama (local open-weights models) | `ollama:qwen3:8b` | none (`OLLAMA_BASE_URL` to move it) |
| vLLM (your own server) | `vllm:Qwen/Qwen3-32B` | optional `VLLM_API_KEY`, `VLLM_BASE_URL` |
| Anything OpenAI-compatible (LiteLLM proxy, Groq, Together, a gateway) | `compatible:my-model` | `RELAY_COMPATIBLE_BASE_URL`, `RELAY_COMPATIBLE_API_KEY` |

```bash
RELAY_MODEL=openai:gpt-5 RELAY_FALLBACK_MODEL=gemini:gemini-2.5-flash \
RELAY_JUDGE_MODEL=anthropic:claude-opus-5-5 RELAY_MEMORY_MODEL=ollama:qwen3:8b uv run uvicorn app.main:app
```

Model IDs change often, so check each provider's model list. Small local models handle the narrow structured calls
(memory, quarantine, routing) well, but run the eval suite before trusting one with the agent loop: tool calling
quality varies far more across models than chat quality does. Costs for non-Anthropic models come from
`RELAY_PRICES`, a JSON map such as `{"gpt-5": [in, cache_write, cache_read, out]}` with numbers in USD per
million tokens, copied from the provider's pricing page.

How it works: `app/llm.py` keeps one message format (text, tool_use and tool_result blocks) for sessions, evals and
judges. `AnthropicLLM` sends it natively; `OpenAICompatLLM` translates it to Chat Completions and back, including
streamed tool calls, cached-token usage and JSON-schema structured output. `app/providers.py` holds the presets.

## Observe

```bash
docker compose -f docker-compose.yml -f ops/docker-compose.observability.yml up -d
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 uv run uvicorn app.main:app      # traces to Jaeger :16686
uv run python -m mcp_servers.shipping &   # then RELAY_SHIPPING_MCP_URL=http://localhost:8090/mcp
```

Prometheus scrapes `/metrics` on the API and worker; import `ops/grafana/relay-dashboard.json` into Grafana.
CI checks that every metric the alerts and dashboard use exists in the code, and validates the rules and the
Collector config with `promtool` and the Collector itself. **Game day:** `RELAY_FAULT_RATE=0.5` makes half of the
primary model calls fail; watch retries, the breaker, the fallback, and `ProviderErrorsHigh`.

**Not measured yet.** The optimization table in the Lab 5 page needs real model traffic: run the simulator load
with an API key, record cost per conversation, TTFT and turn p95, then enable each optimization (routing is off by
default behind the `routing.enabled` flag) and re-run the PR eval suite to confirm quality holds.

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

PDF parsing (Markdown only), contextual chunk descriptions (needs an API key), model-generated red-team
paraphrases, and measured before/after optimization numbers (need real model traffic).
