# Course landscape review

2026-10-14. How this course compares with the main free and paid alternatives, and what to improve.

## Courses reviewed

| Course | Price | Format | Strengths | Gaps relative to this course |
|---|---|---|---|---|
| [aiengg.dev AI System Design cohort](https://aiengg.dev/) | $2,200 | 6 weeks live, 12 sessions, 45 days support, certificate | Live teaching, mentor support, networking | (Paid; our syllabus mirrors theirs) |
| [LLM Zoomcamp](https://github.com/DataTalksClub/llm-zoomcamp) (DataTalks.Club) | Free | 10 weeks, pre-recorded videos, graded homework, peer-reviewed project, certificate, Slack | Community, homework, leaderboard, open materials | Little on security, deployment, CI/CD, SLOs, multi-tenant access control |
| [Production Agentic RAG](https://github.com/jamwithai/production-agentic-rag-course) (Jam with AI) | Free code; paid walkthrough videos | 7 weekly blog posts + tagged code release per week | Real runnable code per week; BM25-first retrieval; Langfuse; Redis caching; LangGraph agentic RAG with document grading and query rewriting | Single domain (arXiv papers); little on evals rigour, security, CI/CD, multi-tenancy |
| [AI Evals for Engineers & PMs](https://maven.com/parlance-labs/evals) (Hamel Husain, Shreya Shankar) | Paid cohort | Live, 4 weeks | The reference on evals method | Evals only |
| [Anthropic Academy](https://anthropic.skilljar.com/) | Free | Self-paced video courses | Official API, MCP, agent skills, Claude Code | Product-specific; not system design |
| Udemy production agent courses (e.g. LangGraph + FastAPI + Docker, DeepEval + Langfuse) | Low cost | Video | Framework walkthroughs | Framework-tied; vary in depth and currency |
| [LLM Twin](https://github.com/decodingai-magazine/llm-twin-course) / [LLM Engineer's Handbook](https://github.com/PacktPublishing/LLM-Engineers-Handbook) | Free / book | Code + lessons | End-to-end LLMOps on AWS incl. fine-tuning | Less on agents and agent security |

Note: "Jam with AI" here is the Jam with AI Substack (Shirin Khosravi Jam and Shantanu Ladhwe). A search
for the name also returns an unrelated no-code business AI academy (jamout.ai), which is out of scope.

## Where this course is already ahead

- **Breadth of the syllabus in one project**: agents, retrieval, evals, security, deployment, observability,
  and capstone review. No free course found covers all of them.
- **Security depth**: lethal trifecta, dual LLM / CaMeL, red-team suites as CI gates. Absent or thin elsewhere.
- **Evals method** follows current best practice (error analysis, binary judges, kappa calibration, pass^k).
- **Operations**: SLOs, burn-rate alerts, kill switches, runbooks, cost models. Rare in free courses.
- **Worked numbers** in every lesson, now checked against primary sources (see `fact-check.md`).

## Where it is behind, in priority order

1. **No runnable reference code.** Jam with AI and LLM Zoomcamp both ship working code. Plan: build Relay with
   one tagged release per lab (`lab1` to `lab5`), tests that run without an API key, and CI. *In progress.*
2. **No video.** Most learners expect it. Plan: short screen recordings per lab walking through the reference
   code, or invite community contributions.
3. **No graded homework or community.** Zoomcamp's cohorts, leaderboard, and peer review drive completion.
   Plan: GitHub Discussions for Q&A, self-check homework per lab with autograder scripts that run the eval
   suite, and a capstone showcase page.
4. **Agentic RAG specifics**: document grading and adaptive query rewriting loops (as in Jam with AI Week 7)
   deserve a worked example in Week 2.
5. **BM25-first teaching order**: Jam with AI teaches keyword search before vectors. Our Week 2 covers hybrid
   search but could make the "start with BM25 baseline" lesson more explicit.
6. **Newer platform features**: agent skills, tool search, server-side compaction, memory tools, MCP Tasks for
   long-running operations. A short section now exists in the context engineering lesson; each could become
   a lab stretch goal.

## Practices confirmed as current (2026)

- Context engineering as the framing, with smallest-high-signal-context as the rule.
- Evals first, from error analysis, with binary judges calibrated against a domain expert.
- Workflows before agents; multi-agent only for parallel, context-heavy work.
- Hybrid retrieval with reranking; contextual chunk enrichment.
- OpenTelemetry GenAI conventions for tracing (still marked Development).
- MCP 2026-07-28: stateless requests, stdio and Streamable HTTP transports, trace context in `params._meta`.
- Prompt injection treated as an architecture problem; detectors as tripwires only.
