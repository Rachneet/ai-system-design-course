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
| GitHub Actions versions (W4) | Tags that exist: checkout `v7`, setup-uv `v10.0.1` (no `v10` major tag), paths-filter `v4`, sticky-pull-request-comment `v3.0.5` (no `v3` tag) | **FIXED** (were v4, v6, v3, v2). Found by CI: the first fix used major tags that do not exist |
| Burn-rate alerting 14.4 / 6 / 1 (W5) | [SRE workbook](https://sre.google/workbook/alerting-on-slos/): assumes a 30-day window | **FIXED** 28 days to 30 days (error budget 3.4 h to 3.6 h) |
| OTel GenAI attribute names (W5) | [semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai/tree/main/docs/gen-ai): status Development; cache attrs `gen_ai.usage.cache_read.input_tokens` / `cache_write.input_tokens` | **FIXED** attribute name and spec link |
| MCP trace propagation "via headers, `_meta` for stdio" (W5, Lab 5) | OTel MCP convention: `traceparent` in `params._meta` on every transport | **FIXED** |
| MCP transports (W5) | [MCP 2026-07-28 transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports): stdio and Streamable HTTP | OK |

## Inference lesson rebuild (2026-10-14)

Checked while rebuilding the inference lesson, including claims from a popular illustrated inference series that
a reader shared.

| Claim | Source | Status |
|---|---|---|
| Llama 3 70B KV cache 320 KB per token in BF16 | 2 x 80 layers x 8 KV heads x 128 dims x 2 bytes = 327,680 bytes | OK |
| Existing servers used 20 to 38% of KV memory; vLLM wastes under 4%; 2 to 4x throughput | [vLLM paper](https://arxiv.org/abs/2309.06180) | OK |
| Goodput definition; 7.4x more requests or 12.6x tighter SLO | [DistServe, OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin) | OK |
| Character.AI 95% cache rate | Original research post now redirects; quoted consistently by [secondary sources](https://buttondown.com/ainews/archive/ainews-shazeer-et-al-2024); 33x cost reduction confirmed on [Character.AI's blog](https://blog.character.ai/optimizing-ai-inference-at-character-ai/) | ADDED as "reported" |
| GQA 8x smaller cache for Llama 3 70B | 64 query heads, 8 KV heads | OK (only for 70B; 8B is 4x) |
| MLA: KV cache -93.3%, 5.76x max throughput | [DeepSeek-V2](https://arxiv.org/abs/2405.04434), against DeepSeek 67B | OK |
| EAGLE-3 "up to 6.5x faster" | [EAGLE-3](https://arxiv.org/abs/2503.01840): peak single-request speedup; 1.38x throughput at batch 64 in SGLang | **QUALIFIED**: the series presented the peak as the general gain |
| NVFP4 "1% or less loss vs FP8" | [NVIDIA](https://developer.nvidia.com/blog/introducing-nvfp4-for-efficient-and-accurate-low-precision-inference): DeepSeek-R1-0528 on NVIDIA's evals | **QUALIFIED** as one model, vendor benchmark |
| FlashAttention-4: 1,605 TFLOPs/s, 71% on B200 | [arXiv 2603.05451](https://arxiv.org/abs/2603.05451) says 1,613; [Together's blog](https://together.ai/blog/flashattention-4) says 1,605 | USED the paper's figure |
| DeepSeek fleet: 278 peak / 226.75 average nodes; 73.7k input and 14.8k output tok/s per node; 56.3% cache hits; $87,072 cost; $562,027 theoretical revenue | [DeepSeek inference system overview](https://github.com/deepseek-ai/open-infra-index/blob/main/202502OpenSourceWeek/day_6_one_more_thing_deepseekV3R1_inference_system_overview.md) | OK, with DeepSeek's caveats that revenue is theoretical |
| "$0.30 per 1M output tokens" | $16/h / 53.3M tokens/h for a decode node | **QUALIFIED**: decode GPUs only |
| DeepSeek-V3: 671B total, 37B active, 8 of 256 routed experts + 1 shared; decode EP144 over 18 nodes, 2 routed + 1 shared per GPU | [DeepSeek-V3 report](https://arxiv.org/abs/2412.19437) and the overview above | OK |
| H100 SXM 989 TFLOPS dense BF16, 3.35 TB/s | [NVIDIA H100](https://www.nvidia.com/en-us/data-center/h100/) | OK |
| "Distilled 8B over 10x cheaper with similar quality" | No source given | **NOT USED**; the lesson states the principle and DeepSeek's released distilled sizes |

## Weeks 11 and 12, and Under the hood (2026-10-15)

| Claim (lesson) | Source | Status |
|---|---|---|
| Permission rules evaluated deny, then ask, then allow; specificity does not change the order; modes default, acceptEdits, plan, auto, dontAsk, bypassPermissions (W11 harness) | [Claude Code permissions](https://code.claude.com/docs/en/permissions) | OK |
| Bash rules "isn't a security boundary around the program" (W11 harness, Foundry threat model) | Same page | OK; the lesson does not claim Claude Code chains commands, since it splits compound commands |
| PreToolUse hook exit code 2 blocks the call; stderr is the reason (W11 harness) | [Claude Code hooks](https://code.claude.com/docs/en/hooks) | OK |
| Sandboxing: filesystem and network isolation, bubblewrap and seatbelt, "reduces permission prompts by 84%" (W11 harness) | [Anthropic engineering, 2025-10-20](https://www.anthropic.com/engineering/claude-code-sandboxing) | OK |
| Codex: setup scripts with internet, agent internet off by default (W11 harness, Foundry ADR 0001) | [Codex agent internet access](https://developers.openai.com/codex/cloud/agent-internet) | OK |
| AGENTS.md: origin across Codex, Amp, Jules, Cursor, Factory; stewarded by the Agentic AI Foundation under the Linux Foundation; nearest file wins (W11 harness) | [agents.md](https://agents.md/) | OK |
| SWE-agent "significantly enhances an agent's ability to create and edit code files"; Agentless 32% on SWE-bench Lite (W11 harness) | [arXiv 2405.15793](https://arxiv.org/abs/2405.15793), [arXiv 2407.01489](https://arxiv.org/abs/2407.01489) | OK |
| SWE-bench: 2,294 problems, 12 repositories, best model 1.96% (W11 evals) | [arXiv 2310.06770](https://arxiv.org/abs/2310.06770) | OK |
| Verified: 500 tasks screened by professional developers, August 2024 (W11 evals) | [swebench.com/verified](https://swebench.com/verified); OpenAI announcement via search | OK |
| OpenAI stopped reporting Verified in February 2026, citing flawed tests and contamination, and recommended SWE-bench Pro (W11 evals, Foundry ADR 0004) | OpenAI post (403 to automated fetches; confirmed through its developer announcement and coverage) | OK, stated without the subset-audit percentages, which are easy to misquote |
| A claim that OpenAI later withdrew the Pro recommendation | One secondary source only | **NOT USED** |
| SWE-Bench Pro: 1,865 problems, 41 repositories, public, held-out and commercial sets (W11 evals) | [arXiv 2509.16941](https://arxiv.org/abs/2509.16941) | OK |
| METR 2025: 16 developers, 246 issues, 19% longer, expected 24% faster, believed 20% faster (W11 evals) | [METR, 2025-07-10](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/) | OK |
| METR 2026: 57 developers; returning -18% (-38% to +9%), new -4% (-15% to +9%); "an unreliable signal" (W11 evals) | [METR, 2026-02-24](https://metr.org/blog/2026-02-24-uplift-update/) | OK |
| Package hallucination: at least 5.2% commercial, 21.7% open-source, 205,474 unique names (W12 security) | [arXiv 2406.10279](https://arxiv.org/abs/2406.10279) | OK; a model count was removed because the abstract does not state it |
| SLSA provenance definition and fields (W12 factory) | [SLSA v1.0 provenance](https://slsa.dev/spec/v1.0/provenance) | OK |
| Under the hood: tokenizer gaps up to 15x (Petrov et al.), self-consistency +17.9% GSM8K, LoRA 10,000x fewer trainable parameters and 3x less memory, Snell et al. 4x and 14x, nucleus sampling, batch-size nondeterminism, reasoning tokens billed as output (OpenAI, Anthropic) | Papers and docs linked in each lesson | OK |
| Raschka chapter mapping: ch. 2 text, ch. 3 attention, ch. 5 decoding (5.3 temperature, top-k), ch. 6 and 7 fine-tuning, appendix E LoRA; reasoning book chapters 4 to 8 | His repositories' READMEs and notebooks | OK |

## Not yet verified (pass 2)

- Lab code has not been executed. The reference implementation (in progress) will replace snippets with tested code.
- Claims attributed to frameworks and tools in passing (LangGraph checkpointers, GPTCache, Presidio features) were not re-read.
- Narrative statements of practice (for example "most teams alert on too much") are judgement, not citable fact.
