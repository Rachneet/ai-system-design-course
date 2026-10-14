---
id: resources
week: 7
kind: page
title: Reading list
short: Reading list
summary: Every free resource used in the course, grouped by topic, with a note on why each one is worth your time.
---

All links are free to read. Starred items (★) are the ones to read if you only have time for a few. The course is provider-neutral: where one vendor has a good guide, the equivalent from other providers and from the open-model world sits next to it, so you can learn on whichever stack you use.

## Other free courses worth taking alongside this one

- [LLM Zoomcamp](https://github.com/DataTalksClub/llm-zoomcamp), DataTalks.Club. 10 weeks, video lectures, graded homework in cohorts, strong on RAG, evaluation, and monitoring.
- [Production Agentic RAG course](https://github.com/jamwithai/production-agentic-rag-course), Jam with AI. A 7-week build of an arXiv research assistant with a tagged code release per week: BM25 first, then hybrid search, Langfuse, caching, and LangGraph agentic RAG. Weekly write-ups on [the Jam with AI Substack](https://jamwithai.substack.com/).
- [Anthropic Academy](https://anthropic.skilljar.com/) and [Anthropic's course notebooks](https://github.com/anthropics/courses): the Claude API, tool use, MCP, and agent skills.
- [5-Day AI Agents Intensive](https://www.kaggle.com/learn-guide/5-day-agents) and [5-Day Gen AI Intensive](https://www.kaggle.com/learn-guide/5-day-genai), Google and Kaggle. Self-paced guides that pair Google whitepapers with notebooks; the agents run (November 2025) drew over 1.5 million learners ([Google's recap](https://blog.google/technology/developers/ai-agents-intensive-recap/)).
- [AI Agents for Beginners](https://github.com/microsoft/ai-agents-for-beginners), Microsoft. 18 open (MIT) lessons from tool use and agentic RAG to memory, protocols, production and security; its samples need an Azure account. The companion [Generative AI for Beginners](https://github.com/microsoft/generative-ai-for-beginners) has 21 lessons on the basics.
- [Hugging Face Agents Course](https://huggingface.co/learn/agents-course), the best free route to agents on open-weights models, with smolagents, LangGraph and LlamaIndex units.
- [OpenAI Cookbook](https://developers.openai.com/cookbook), runnable notebooks for tool calling, evals, retrieval and agents.
- [LLM Twin course](https://github.com/decodingai-magazine/llm-twin-course), Decoding AI, and the companion [LLM Engineer's Handbook code](https://github.com/PacktPublishing/LLM-Engineers-Handbook): end-to-end LLMOps on AWS.
- [Gaurav Sen's YouTube channel](https://www.youtube.com/@gkcs): short videos on AI system design topics such as multi-agent failures, chatbot latency, long context windows, and speculative decoding. His [AI Engineering course](https://interviewready.io/course-page/ai-engineering) on InterviewReady ($55) covers LLM internals, optimisations, and reasoning.
- [Krish Naik's Agentic AI roadmap](https://github.com/krishnaik06/Roadmap-To-Learn-Agentic-AI): free YouTube playlists for LangChain, LangGraph, MCP, CrewAI, and AutoGen. Strongest for breadth across frameworks.
- [LangChain Academy](https://academy.langchain.com/) for LangGraph, and [DeepLearning.AI short courses](https://www.deeplearning.ai/short-courses/) for one-to-two-hour introductions to specific tools.

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
- [Context Rot](https://www.trychroma.com/research/context-rot), Chroma research.
- [12-factor agents](https://github.com/humanlayer/12-factor-agents), HumanLayer.
- [LLM Powered Autonomous Agents](https://lilianweng.github.io/posts/2023-06-23-agent/), Lilian Weng.
- [ReAct](https://arxiv.org/abs/2210.03629), [MemGPT](https://arxiv.org/abs/2310.08560), [Generative Agents](https://arxiv.org/abs/2304.03442), [CoALA](https://arxiv.org/abs/2309.02427): foundational papers.
- [LangGraph memory overview](https://docs.langchain.com/oss/python/langgraph/memory).
- Open-source memory layers to study: [Mem0](https://github.com/mem0ai/mem0), [Letta](https://github.com/letta-ai/letta), [Graphiti](https://github.com/getzep/graphiti).
- ★ [A practical guide to building agents](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf), OpenAI. 34 pages on when an agent is worth it, single agent before multi-agent, and guardrails as layered defence. Read it next to Anthropic's essay: they agree.
- [Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/abs/2503.13657), the MAST taxonomy: 14 failure modes from 1,600+ annotated traces, a ready-made checklist for reading multi-agent traces.

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
- [MCP security best practices](https://modelcontextprotocol.io/specification/2026-07-28/basic/security_best_practices).
- [Adversarial attacks on LLMs](https://lilianweng.github.io/posts/2023-10-25-adv-attack-llm/), Lilian Weng.
- [Embrace The Red](https://embracethered.com/blog/), real-world AI exploit write-ups.
- [MITRE ATLAS](https://atlas.mitre.org/), adversarial technique catalogue.
- Tools: [AgentDojo](https://github.com/ethz-spylab/agentdojo), [garak](https://github.com/NVIDIA/garak), [PyRIT](https://github.com/Azure/PyRIT), [promptfoo red teaming](https://www.promptfoo.dev/docs/red-team/), [Presidio](https://microsoft.github.io/presidio/), [NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails), [Guardrails AI](https://github.com/guardrails-ai/guardrails).
- ★ [Purple Llama](https://github.com/meta-llama/PurpleLlama), Meta's open trust and safety tools, which work in front of any model: [Llama Guard 4](https://huggingface.co/meta-llama/Llama-Guard-4-12B) (a 12B multimodal input and output classifier on the MLCommons hazard taxonomy), [Llama Prompt Guard 2](https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M) (86M and 22M injection and jailbreak detectors), and CyberSecEval benchmarks.
- [OpenAI Model Spec](https://model-spec.openai.com/), how one lab says its models should rank system, developer and user instructions (the chain of command). Useful vocabulary when you design your own instruction hierarchy.
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

- ★ [OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai/tree/main/docs/gen-ai) and [OTel Python](https://opentelemetry.io/docs/languages/python/).
- [OpenLLMetry](https://github.com/traceloop/openllmetry), [Langfuse](https://langfuse.com/docs), [Arize Phoenix](https://github.com/Arize-ai/phoenix).
- ★ Google SRE: [Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/), [Service Level Objectives](https://sre.google/sre-book/service-level-objectives/), [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/), the [full SRE book](https://sre.google/sre-book/table-of-contents/).
- [Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/), Amazon Builders' Library.
- [Circuit Breaker](https://martinfowler.com/bliki/CircuitBreaker.html), Martin Fowler.
- Prompt caching, three ways: [Anthropic](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) (marked breakpoints), [OpenAI](https://developers.openai.com/api/docs/guides/prompt-caching) (automatic, with explicit breakpoints on newer models), [Gemini](https://ai.google.dev/gemini-api/docs/caching) (implicit by default, explicit cache objects optional). Compare minimum lengths and write prices before you design your prompt order.
- [Artificial Analysis](https://artificialanalysis.ai/) for model speed and price comparisons.
- [Prometheus](https://prometheus.io/docs/introduction/overview/), [Grafana](https://grafana.com/docs/grafana/latest/), [Sentry](https://docs.sentry.io/).

## Protocols

- ★ [MCP specification](https://modelcontextprotocol.io/specification/latest) (current version 2026-07-28), the source of truth for how tools, resources and prompts reach any agent, with its own security principles.
- [A2A specification](https://a2a-protocol.org/latest/specification/) (v1.0), for agents that delegate to agents another team or vendor runs.
- [Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp), Anthropic, on cutting tool-definition tokens by letting the agent call tools from code.

## Provider docs: tool calling and agent SDKs

The same concepts, in each provider's words. Read the one you build on, and skim one other to see what is a standard and what is a vendor choice.

- Tool calling: [OpenAI](https://developers.openai.com/api/docs/guides/function-calling), [Gemini](https://ai.google.dev/gemini-api/docs/function-calling), [Claude](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview). The JSON schema shapes differ slightly; the loop is the same.
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/): agents, handoffs, guardrails, sessions and tracing in a small API, with adapters (LiteLLM, Any-LLM) for non-OpenAI models.
- [Google Agent Development Kit (ADK)](https://adk.dev/): open-source, in Python, TypeScript, Go, Java and Kotlin, works with Gemini and other models, with built-in evaluation and user simulation.
- [Microsoft Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/overview): a managed runtime for prompt agents or your own containerised agent (Agent Framework, LangGraph, OpenAI or Anthropic SDKs), with tracing, evaluation and A2A endpoints. A good map of what "managed agents" means.
- [Claude cookbooks](https://github.com/anthropics/claude-cookbooks) and the [OpenAI Cookbook](https://developers.openai.com/cookbook): worked notebooks per provider.
- [Gemini's OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai): call Gemini with the OpenAI client by changing the base URL, a concrete example of the OpenAI-compatible API.
- Other frameworks to compare: [Pydantic AI](https://github.com/pydantic/pydantic-ai), [smolagents](https://huggingface.co/docs/smolagents/index) (Hugging Face; code-writing agents, any model through Inference Providers, LiteLLM, Transformers or Ollama), [LlamaIndex](https://docs.llamaindex.ai/en/stable/).

## Open models, serving, and gateways

- ★ [vLLM OpenAI-compatible server](https://docs.vllm.ai/en/latest/serving/online_serving/): `vllm serve <model>` gives Llama, Qwen, DeepSeek or Mistral weights the same chat, Responses and embeddings endpoints your app already calls.
- [SGLang](https://docs.sglang.io/), high-throughput serving with RadixAttention prefix caching, used for large MoE deployments.
- [Ollama](https://ollama.com/) and its [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility) (`http://localhost:11434/v1`): the quickest way to run an open model on a laptop for development and evals.
- [OGX](https://github.com/ogx-ai/ogx), formerly Meta's Llama Stack: an open-source, OpenAI-compatible server that adds vector stores, files, tool calling and agent orchestration on top of pluggable model providers.
- [Hugging Face Inference Providers](https://huggingface.co/docs/inference-providers/index): open-weights models on many hosts (Groq, Together, Cerebras, Fireworks and others) behind one token and an OpenAI-compatible router, with `:fastest` and `:cheapest` selection.
- [OpenRouter](https://openrouter.ai/docs/quickstart): hundreds of hosted and open models through one OpenAI-compatible endpoint, with automatic fallbacks.
- [LiteLLM](https://docs.litellm.ai/docs/): a self-hosted gateway over 100+ providers in the OpenAI format, with retries, fallbacks, virtual keys, budgets and spend tracking per team.
- Inference background: [Optimizing your LLM in production](https://huggingface.co/blog/optimize-llm), [PagedAttention](https://arxiv.org/abs/2309.06180), [speculative decoding](https://arxiv.org/abs/2211.17192), and this course's [inference lesson](#w5-inference).
