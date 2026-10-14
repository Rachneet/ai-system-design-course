# Fact-check log

Pass 1, 2026-10-14. Each specific, checkable claim in the course was compared with its primary source.
Status: **OK** (matches source), **FIXED** (was wrong or outdated, now corrected), **ADDED** (made more precise
with sourced figures).

## Model pricing and API behaviour

| Claim (lesson) | Source | Status |
|---|---|---|
| Opus 5.5 $4/$20, Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50 per M tokens (several) | [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing) | OK |
| Sonnet 5.5 cache read $0.20/M (W5 caching, W5 monitoring, W6 cost model) | Pricing page: $0.10/M (0.05x base) | **FIXED**, all three examples recomputed |
| Haiku 5.5 cache read $0.01/M (W5 monitoring, flagged "check") | Pricing page: $0.01/M | OK, flag removed |
| Cost function ignored cache writes (W5 monitoring) | Prompt caching docs: writes 1.25x (5 min) / 2x (1 h); `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` are disjoint | **FIXED** |
| Caching example ignored write premium (W5 caching) | Same | **FIXED**: $0.029 became $0.032 |
| Design B/C costs (W6) | Recomputed with $0.10 reads and 1.25x writes | **FIXED**: B $0.075 to $0.079, C $0.034 to $0.035, monthly $113k to $119k and $51k to $53k |
| "Caching discount often 90%" (W1 context, W5 table) | 0.1x on most models, 0.05x on Opus 5.5 / Sonnet 5.5 | **FIXED**: "90 to 95%" |
| Cache TTL 5 min, longer option; minimum prefix | Prompt caching docs: 5 min default refreshed on read, 1 h option, 512-token minimum on current models | ADDED |
| Haiku 5.5 long-prompt pricing | Pricing page: higher rates above 100k-token prompts | ADDED (W5 monitoring) |
| Batch API about half price | Pricing page: 50% off | OK |
| SDK calls: `messages.parse(output_format=...)`, `strict: True`, async `messages.stream` with `text_stream` / `get_final_message()`, exception classes | Claude API SDK docs | OK |
| Agent loop treated any non-`tool_use` stop as a final answer (W1 lesson, Lab 1) | API docs: `max_tokens` and `refusal` stop reasons need handling | **FIXED** |

## Agents and context

| Claim | Source | Status |
|---|---|---|
| Five workflow patterns; workflow vs agent definitions (W1) | [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | OK |
| Multi-agent uses ~15x chat tokens (W1) | [Multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system): agents ~4x, multi-agent ~15x | ADDED the 4x figure |
| Multi-agent weak for shared-context and coding tasks (W1) | Same article | OK |
| Context rot: accuracy degrades with input length (W1) | [Chroma](https://www.trychroma.com/research/context-rot): 18 models, less reliable as input grows | OK, **URL updated** (old one redirects) |
| Provider context features (W1 context) | Claude API docs: context editing, compaction, memory tool, tool search | ADDED new section |

## Retrieval

| Claim | Source | Status |
|---|---|---|
| Contextual retrieval "large reductions" (W2) | [Anthropic](https://www.anthropic.com/engineering/contextual-retrieval): -35% / -49% / -67% top-20 failure rate | ADDED exact figures |
| pgvector 0.8 added iterative scans; HNSW defaults (W2) | [pgvector README](https://github.com/pgvector/pgvector): 0.8.0, `hnsw.iterative_scan`; m=16, ef_construction=64, ef_search=40 | OK, ADDED defaults, 10%-filter example, 2,000-dim limit, `halfvec` |
| Element-based chunking beat fixed-size on financial reports (W2) | [arXiv 2402.05131](https://arxiv.org/abs/2402.05131) | OK |
| RRF with k=60 (W2) | [Cormack et al.](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) | OK |

## Evals and security

| Claim | Source | Status |
|---|---|---|
| Binary pass/fail, open and axial coding, first failure, benevolent dictator, generic metrics warning, dimensions for synthetic data (W3) | [Evals FAQ](https://hamel.dev/blog/posts/evals-faq/) | OK, ADDED "at least 100 traces, first 30 yourself" |
| τ-bench: simulated users, DB state comparison, pass^k (W1, W3) | [arXiv 2406.12045](https://arxiv.org/abs/2406.12045) | OK, ADDED <50% success, pass^8 <25% retail |
| Judge biases: position, verbosity, self-preference (W3) | [arXiv 2306.05685](https://arxiv.org/abs/2306.05685): position, verbosity, self-enhancement; >80% agreement, same as human-human | ADDED |
| Detectable regression ≈ 4 points at n=200 (W3) | Two-sample standard error | **FIXED** to ≈ 5 points with the working shown |
| CaMeL design (W3) | [arXiv 2503.18813](https://arxiv.org/abs/2503.18813): P-LLM, Q-LLM, interpreter with provenance and policies; 77% vs 84% on AgentDojo | ADDED |
| MCP security best practices link (W3, library) | Latest spec revision is 2026-07-28 | **FIXED** link |

## Deployment and operations

| Claim | Source | Status |
|---|---|---|
| Cloud Run timeout up to 60 min (W4) | [Cloud Run docs](https://docs.cloud.google.com/run/docs/configuring/request-timeout): default 5 min, max 60 | OK |
| Cloud Run worker pools need no port (Lab 4) | [Worker pools docs](https://docs.cloud.google.com/run/docs/deploy-worker-pools): no endpoint, no autoscaling | ADDED "no autoscaling" and command |
| Dockerfile (W4) | [uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/): copy `/uv /uvx`, cache mounts, `--frozen` then `--locked` | **FIXED** to current pattern, uv pinned to 0.12.21 |
| GitHub Actions versions (W4) | Latest releases: checkout v7, setup-uv v10, paths-filter v4, sticky-pull-request-comment v3 | **FIXED** (were v4, v6, v3, v2) |
| Burn-rate alerting 14.4 / 6 / 1 (W5) | [SRE workbook](https://sre.google/workbook/alerting-on-slos/): assumes a 30-day window | **FIXED** 28 days to 30 days (error budget 3.4 h to 3.6 h) |
| OTel GenAI attribute names (W5) | [semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai/tree/main/docs/gen-ai): status Development; cache attrs `gen_ai.usage.cache_read.input_tokens` / `cache_write.input_tokens` | **FIXED** attribute name and spec link |
| MCP trace propagation "via headers, `_meta` for stdio" (W5, Lab 5) | OTel MCP convention: `traceparent` in `params._meta` on every transport | **FIXED** |
| MCP transports (W5) | [MCP 2026-07-28 transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports): stdio and Streamable HTTP | OK |

## Not yet verified (pass 2)

- Lab code has not been executed. The reference implementation (in progress) will replace snippets with tested code.
- Claims attributed to frameworks and tools in passing (LangGraph checkpointers, GPTCache, Presidio features) were not re-read.
- Narrative statements of practice (for example "most teams alert on too much") are judgement, not citable fact.
