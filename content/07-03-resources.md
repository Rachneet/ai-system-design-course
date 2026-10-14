---
id: resources
week: 7
kind: page
title: Reading list
short: Reading list
summary: Every free resource used in the course, grouped by topic, with a note on why each one is worth your time.
---

All links are free to read. Starred items (★) are the ones to read if you only have time for a few.

## Foundations

- ★ [Intro to Large Language Models](https://www.youtube.com/watch?v=zjkBMFhNj_g), Andrej Karpathy. One hour, the best mental model of what an LLM is.
- ★ [Building A Generative AI Platform](https://huyenchip.com/2024/07/25/genai-platform.html), Chip Huyen. A reference architecture for everything in this course.
- [AI Engineering book resources](https://github.com/chiphuyen/aie-book), Chip Huyen's companion repo.
- ★ [What We Learned from a Year of Building with LLMs](https://applied-llms.org/), practitioners' lessons across tactics, operations, and strategy.
- [Patterns for Building LLM-based Systems & Products](https://eugeneyan.com/writing/llm-patterns/), Eugene Yan.
- [Emerging Patterns in Building GenAI Products](https://martinfowler.com/articles/gen-ai-patterns/), martinfowler.com.
- [LLM Course](https://github.com/mlabonne/llm-course), Maxime Labonne. A roadmap for deeper ML background.
- [System Design Primer](https://github.com/donnemartin/system-design-primer), for general distributed systems design.

## Agents and context

- ★ [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents), Anthropic.
- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system), Anthropic.
- [Don't build multi-agents](https://cognition.ai/blog/dont-build-multi-agents), Cognition.
- ★ [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents), Anthropic.
- [Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents), Anthropic.
- [Context Engineering for Agents](https://rlancemartin.github.io/2025/06/23/context_engineering/), Lance Martin.
- [The New Skill in AI is Context Engineering](https://www.philschmid.de/context-engineering), Philipp Schmid.
- [Context Rot](https://research.trychroma.com/context-rot), Chroma research.
- [12-factor agents](https://github.com/humanlayer/12-factor-agents), HumanLayer.
- [LLM Powered Autonomous Agents](https://lilianweng.github.io/posts/2023-06-23-agent/), Lilian Weng.
- [ReAct](https://arxiv.org/abs/2210.03629), [MemGPT](https://arxiv.org/abs/2310.08560), [Generative Agents](https://arxiv.org/abs/2304.03442), [CoALA](https://arxiv.org/abs/2309.02427): foundational papers.
- [LangGraph memory overview](https://docs.langchain.com/oss/python/langgraph/memory).
- Open-source memory layers to study: [Mem0](https://github.com/mem0ai/mem0), [Letta](https://github.com/letta-ai/letta), [Graphiti](https://github.com/getzep/graphiti).
- Free courses: [Hugging Face Agents Course](https://huggingface.co/learn/agents-course), [AI Agents for Beginners](https://github.com/microsoft/ai-agents-for-beginners).

## Retrieval

- ★ [Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval), Anthropic.
- ★ [Systematically Improving Your RAG](https://jxnl.co/writing/2024/05/22/systematically-improving-your-rag/), Jason Liu.
- [pgvector](https://github.com/pgvector/pgvector) and [pgvector-python](https://github.com/pgvector/pgvector-python).
- [HNSW explained](https://www.pinecone.io/learn/series/faiss/hnsw/), Pinecone, and the [HNSW paper](https://arxiv.org/abs/1603.09320).
- [Hybrid search explained](https://weaviate.io/blog/hybrid-search-explained), Weaviate.
- [Reciprocal Rank Fusion](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf), the original paper.
- [Retrieve and re-rank](https://sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html), Sentence-Transformers.
- [MTEB leaderboard](https://huggingface.co/spaces/mteb/leaderboard) for embedding models.
- [Qdrant filtering](https://qdrant.tech/documentation/concepts/filtering/) and [Postgres full-text search](https://www.postgresql.org/docs/current/textsearch.html).
- [Docling](https://github.com/docling-project/docling) for document parsing.
- Papers: [RAG](https://arxiv.org/abs/2005.11401), [Lost in the Middle](https://arxiv.org/abs/2307.03172), [HyDE](https://arxiv.org/abs/2212.10496), [RAPTOR](https://arxiv.org/abs/2401.18059), [ColBERT](https://arxiv.org/abs/2004.12832), [RAG survey](https://arxiv.org/abs/2312.10997), [Financial report chunking](https://arxiv.org/abs/2402.05131).
- Authorization: [OpenFGA](https://openfga.dev/) and the [Zanzibar paper](https://research.google/pubs/zanzibar-googles-consistent-global-authorization-system/).

## Evals

- ★ [Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/), Hamel Husain.
- ★ [AI Evals FAQ](https://hamel.dev/blog/posts/evals-faq/), Hamel Husain and Shreya Shankar.
- [Creating a LLM-as-a-Judge That Drives Business Results](https://hamel.dev/blog/posts/llm-judge/), Hamel Husain.
- [Evaluating the Effectiveness of LLM-Evaluators](https://eugeneyan.com/writing/llm-evaluators/), Eugene Yan.
- ★ [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), Anthropic.
- Papers: [τ-bench](https://arxiv.org/abs/2406.12045), [Judging LLM-as-a-Judge](https://arxiv.org/abs/2306.05685), [Who Validates the Validators?](https://arxiv.org/abs/2404.12272), [RAGAS](https://arxiv.org/abs/2309.15217), [AgentBench](https://arxiv.org/abs/2308.03688).
- Tools: [promptfoo](https://github.com/promptfoo/promptfoo), [Inspect](https://inspect.aisi.org.uk/), [DeepEval](https://github.com/confident-ai/deepeval), [RAGAS](https://docs.ragas.io/), [τ-bench code](https://github.com/sierra-research/tau-bench), [OpenAI evals](https://github.com/openai/evals).

## Security

- ★ [The lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/), Simon Willison, and his [prompt injection series](https://simonwillison.net/series/prompt-injection/).
- [The Dual LLM pattern](https://simonwillison.net/2023/Apr/25/dual-llm-pattern/), Simon Willison.
- ★ [Design Patterns for Securing LLM Agents against Prompt Injections](https://arxiv.org/abs/2506.08837).
- [Defeating Prompt Injections by Design (CaMeL)](https://arxiv.org/abs/2503.18813).
- [Indirect prompt injection](https://arxiv.org/abs/2302.12173), Greshake et al.
- [OWASP Top 10 for LLM Applications](https://genai.owasp.org/llm-top-10/) and [OWASP API Security Top 10](https://owasp.org/API-Security/).
- [MCP security best practices](https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices).
- [Adversarial attacks on LLMs](https://lilianweng.github.io/posts/2023-10-25-adv-attack-llm/), Lilian Weng.
- [Embrace The Red](https://embracethered.com/blog/), real-world AI exploit write-ups.
- [MITRE ATLAS](https://atlas.mitre.org/), adversarial technique catalogue.
- Tools: [AgentDojo](https://github.com/ethz-spylab/agentdojo), [garak](https://github.com/NVIDIA/garak), [PyRIT](https://github.com/Azure/PyRIT), [promptfoo red teaming](https://www.promptfoo.dev/docs/red-team/), [Presidio](https://microsoft.github.io/presidio/), [Llama Guard 3](https://huggingface.co/meta-llama/Llama-Guard-3-8B), [NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails), [Guardrails AI](https://github.com/guardrails-ai/guardrails).
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework).

## Deployment and operations

- [FastAPI](https://fastapi.tiangolo.com/), including [security](https://fastapi.tiangolo.com/tutorial/security/) and [Docker](https://fastapi.tiangolo.com/deployment/docker/) guides.
- [uv with Docker](https://docs.astral.sh/uv/guides/integration/docker/) and [with GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/).
- [The Twelve-Factor App](https://12factor.net/).
- [Docker build best practices](https://docs.docker.com/build/building/best-practices/).
- [GitHub Actions](https://docs.github.com/en/actions) and its [security hardening guide](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions).
- [Cloud Run](https://cloud.google.com/run/docs), [Fly.io](https://fly.io/docs/), [Render free tier](https://render.com/docs/free), [Kubernetes autoscaling](https://kubernetes.io/docs/concepts/workloads/autoscaling/).
- ★ [Implementing Stripe-like Idempotency Keys in Postgres](https://brandur.org/idempotency-keys), Brandur Leach.
- [Transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html).
- [Temporal](https://docs.temporal.io/), [arq](https://arq-docs.helpmanual.io/), [RQ](https://python-rq.org/), [Celery](https://docs.celeryq.dev/).
- [SLSA](https://slsa.dev/) for supply-chain integrity.
- [AWS Well-Architected Generative AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/generative-ai-lens.html).

## Observability and scaling

- ★ [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) and [OTel Python](https://opentelemetry.io/docs/languages/python/).
- [OpenLLMetry](https://github.com/traceloop/openllmetry), [Langfuse](https://langfuse.com/docs), [Arize Phoenix](https://github.com/Arize-ai/phoenix).
- ★ Google SRE: [Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/), [Service Level Objectives](https://sre.google/sre-book/service-level-objectives/), [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/), the [full SRE book](https://sre.google/sre-book/table-of-contents/).
- [Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/), Amazon Builders' Library.
- [Circuit Breaker](https://martinfowler.com/bliki/CircuitBreaker.html), Martin Fowler.
- [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), Claude Platform docs.
- [LiteLLM](https://docs.litellm.ai/docs/) for multi-provider routing.
- [Artificial Analysis](https://artificialanalysis.ai/) for model speed and price comparisons.
- [Prometheus](https://prometheus.io/docs/introduction/overview/), [Grafana](https://grafana.com/docs/grafana/latest/), [Sentry](https://docs.sentry.io/).

## Protocols and SDKs

- [Model Context Protocol](https://modelcontextprotocol.io/).
- [Claude tool use docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) and [Claude cookbooks](https://github.com/anthropics/claude-cookbooks).
- Agent frameworks to compare: [Pydantic AI](https://github.com/pydantic/pydantic-ai), [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/), [Google ADK](https://google.github.io/adk-docs/), [LlamaIndex](https://docs.llamaindex.ai/en/stable/).
- [Ollama](https://ollama.com/) for running open models locally.
