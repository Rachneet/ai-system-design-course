# Enterprise track: plan

Status: E1 to E5 built, 2026-10-15. Proposed 2026-10-14. Builds on the six core weeks and the Relay reference implementation.

## Why this track

The large platforms now sell the same set of components for running agents inside companies. Primary sources:

| Component | Google Cloud (Gemini Enterprise Agent Platform, Next '26) | AWS (Bedrock AgentCore) |
|---|---|---|
| Registry | Agent Registry: "indexing every internal agent and tool across your organization" | Registry: catalog of agents, MCP servers, tools, skills; publish, review, approve; hybrid search |
| Gateway | Agent Gateway: understands MCP and A2A, "centralized, real-time policy enforcement", inline prompt-injection and data-leak protection | Gateway: turns APIs into MCP tools, connects MCP servers, semantic tool search |
| Identity | Agent Identity: "a unique cryptographic ID and well defined authorization policies" per agent | Identity: inbound and outbound auth, works with existing IdPs |
| Policy | (via Gateway) | Policy: deterministic rules written in Cedar that "intercept every tool call before execution" |
| Quality | Agent Observability | Observability (OpenTelemetry), Evaluations, Optimization (versioned configs, A/B tests) |

Anthropic's [Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) define a portable
package for agent know-how (`SKILL.md` with `name` and `description` frontmatter, instructions, scripts,
resources, loaded by progressive disclosure) and warn that skills must be audited like installed software.
The [MCP registry](https://registry.modelcontextprotocol.io/) defines `server.json` metadata for MCP servers, and
[A2A](https://a2a-protocol.org/latest/) defines Agent Cards for agent discovery.

Students cannot learn how these work from managed services, which hide the design. This track builds open,
tested versions of each component and runs a real multi-tenant workload on them.

## Projects

Each project is a separate service in a `platform/` monorepo, built to the same engineering standard (below),
with its own design doc, threat model, ADRs, OpenAPI spec, tests, eval suite where relevant, container, and CI.

### E1. Switchboard: AI gateway
One endpoint between every internal app and every model provider. **Built:** `platform/switchboard` (35 tests, CI).
- Anthropic- and OpenAI-compatible APIs, streaming passthrough, prompt-cache-safe (no prefix rewriting)
- Virtual keys with hierarchical budgets (org → team → app), RPM and TPM limits, model allow-lists
- Routing, retries, circuit breakers, cross-provider fallback; per-tenant data residency rules
- PII detection and redaction policies; prompt and response audit log with retention controls
- Usage metering and cost chargeback per team; OpenTelemetry GenAI spans; Prometheus metrics
- Load-tested overhead budget (target: under 10 ms p95 added latency, excluding provider time)

### E2. Atlas: agent, tool and skill registry
The catalog that says what exists, who owns it, and whether it is approved. **Built:** `platform/atlas` (28 tests, CI).
- Resource types: A2A Agent Cards, MCP servers (`server.json`-compatible), Agent Skills (`SKILL.md` packages)
- Versioning, ownership, publish → automated checks → human review → approved → deprecated lifecycle
- Automated checks: schema validation, skill static analysis (network calls, file writes, shell use, secrets),
  licence allow-list, and eval gates (no approval below a score threshold). Built. Planned: dependency scanning,
  signature verification, and pinning each server's tool list so a changed tool description needs review again
- Hybrid search (reuses Relay's retrieval), RBAC, audit log, and a sync from the public MCP registry
  into a private, curated sub-registry

### E3. Checkpoint: MCP and agent gateway with policy
The control point every tool call passes through. **Built:** `platform/checkpoint` (9 tests, CI).
- Fronts approved MCP servers from Atlas behind one MCP endpoint per agent
- Agent identity: each agent authenticates with its own credentials; user context flows with OAuth token
  exchange (on-behalf-of), so tools see both "which agent" and "for which user"
- Policy as code (Cedar): which agent may call which tool, with which arguments, for which user, and when a
  human must approve; every decision logged
- Tool-output scanning for injection and secrets, egress allow-lists, rate limits per agent and tool
- Tool search to keep large tool catalogs out of context

### E4. Helpdesk OS: a multi-tenant support platform on E1-E3
The workload that proves the platform: agents that resolve people's issues end to end. **Built:** `platform/helpdesk`
(73 tests, CI; the tests run the real E1 to E3 in process).
- Tenants: an employee IT and HR helpdesk and an external customer-support desk, isolated per tenant
- Specialist agents (IT access, HR policy, billing, returns) built from skills, coordinated over A2A, with
  handoffs and a human console for approvals and escalations
- Real integrations through MCP: ticketing, identity provider (account unlock, access requests), knowledge base,
  order systems; every write through Checkpoint policy
- SSO, audit, SLOs, eval suites per agent, red-team suites per tenant, cost per resolved ticket

### E5. Foundry: a coding-agent harness and a software factory on E1-E4
The workload companies run agents on first: issues in, reviewed and tested changes out. **Built:** `platform/foundry`.
- Harness: an agent loop over five tools (read, list, search, edit, run) in a throwaway clone of the repository; a
  permission policy (deny, then ask, then allow) and pre-tool hooks; a sandbox with a scrubbed environment, time and
  output limits and a configurable wrapper (bubblewrap, `sandbox-exec`, a container) for real isolation
- Factory: issue to branch; deterministic gates (tests pass, diff size, protected paths, no deleted tests, no
  secrets); a reviewer model that sees only the issue and the diff; merge only when every gate passes, otherwise the
  branch waits for a person; provenance on every change (job, roles, models, prompt digests, gate results)
- Every model call through Switchboard, tagged per job and role, with a token budget per job
- Evals: a task suite built from the repository's own history, not a public leaderboard


Relay moves onto the platform: model calls through Switchboard, tools through Checkpoint, its agent card and
skills in Atlas. The before/after is a lesson in itself.

## Course content to add (weeks 7 to 10)

1. AI gateways: virtual keys, budgets, routing, caching, and why the gateway must not break prompt caching
2. Agent identity and authorization: OAuth client credentials, token exchange, on-behalf-of, least privilege
3. Policy as code for agents: Cedar and OPA, deterministic guardrails, approvals, audit
4. Registries and the agent supply chain: skills, MCP servers, agent cards; vetting, signing, SBOMs
5. Multi-agent systems in the enterprise: A2A, handoffs, orchestration patterns, failure modes (MAST)
6. Multi-tenancy for AI: isolation at data, retrieval, memory, cache, and model-key levels
7. Platform engineering for agents: the paved path, templates, golden pipelines, internal developer portal
8. Governance: audit, retention, EU AI Act and NIST AI RMF obligations, model and prompt change control
9. AI FinOps: chargeback, unit economics (cost per resolved issue), budget enforcement
10. Coding-agent harnesses: the loop, the agent-computer interface, context and AGENTS.md, permissions, hooks,
    sandboxes, subagents; evaluating coding agents after SWE-bench Verified (week 11)
11. The software factory: issue to merged change, gates, reviewers, provenance, and the security of agent-written
    code (week 12)

## Engineering standard for every project

- Design doc with C4 diagrams, ADRs, STRIDE threat model, SLOs, and a cost model
- OpenAPI spec as the contract, with contract tests; versioned APIs and deprecation policy
- Alembic migrations (expand and contract), never schema-on-startup
- Structured JSON logs with trace IDs, OpenTelemetry traces, Prometheus metrics, alert rules with runbooks
- Tests: unit, integration (real Postgres), contract, load (k6 or Locust with recorded budgets), chaos (fault
  injection), and evals where a model is involved
- Supply chain: pinned and locked dependencies, `pip-audit`, `bandit`, container scanning (Trivy), SBOM (Syft),
  signed images (cosign), minimal non-root images
- Repository hygiene: CODEOWNERS, PR template with a risk section, Conventional Commits, release notes,
  `SECURITY.md` and a disclosure process
- Infrastructure as code (OpenTofu) with staging and production, and a documented rollback

## Order and effort

| Order | Project | Why this order |
|---|---|---|
| 1 | E1 Switchboard | Smallest surface, immediately useful, and E3 and E4 depend on it |
| 2 | E2 Atlas | E3 needs to know what is approved |
| 3 | E3 Checkpoint | The hardest security work; builds on E1 and E2 |
| 4 | E4 Helpdesk OS | Exercises everything; becomes the capstone |
| 5 | E5 Foundry | Agents that change code: the highest-leverage and highest-risk workload; the final capstone |

Each project ships the same way as Relay's labs: a lesson set, a lab, and a tested reference implementation
with tags per milestone.
