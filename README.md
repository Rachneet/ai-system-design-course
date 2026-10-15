# AI System Design Course

A free, ten-week course on designing production AI systems. Six core weeks cover agents, retrieval, evals, security,
deployment and observability, taught through one application (Relay, a support agent) that grows from a prototype
into a monitored cloud service. A four-week enterprise track then builds the platform companies run agents on, and
a multi-tenant workload on top of it.

- Every week has lessons and a lab; each half of the course ends with a capstone; a library adds design drills, a
  glossary and a reading list
- Every lesson has worked numbers, diagrams, design review questions, and a self-check quiz
- Every linked resource is free (links checked on 2026-10-14)

This is an independent, original course. Its weekly topics follow the public syllabus of paid AI
system design cohorts so that students can study the same ground for free. No paid course material
is reproduced.

## Reference implementations

| Directory | What it is | Taught in |
|---|---|---|
| [`relay/`](relay) | The support agent built through the core weeks, provider-neutral | Weeks 1 to 6 |
| [`platform/switchboard/`](platform/switchboard) | AI gateway: keys, budgets, routing, fallbacks, metering, ticket tags | Week 7 |
| [`platform/atlas/`](platform/atlas) | Registry for MCP servers, A2A agent cards and Agent Skills, with review and pinned tool lists | Week 8 |
| [`platform/checkpoint/`](platform/checkpoint) | MCP gateway: agent and user identity, tenants, Cedar policy, approvals, assertions | Weeks 7 and 8 |
| [`platform/helpdesk/`](platform/helpdesk) | Helpdesk OS, the enterprise capstone: two tenants, six agents, all on the three services above | Weeks 9 and 10 |
| [`under-the-hood/`](under-the-hood) | Tokenizer, KV cache, sampling, LoRA and test-time compute, each from scratch in numpy | Optional lessons |

Each has its own tests, CI, threat model and ADRs. Helpdesk's tests run the other three for real, in process.

## Layout

```
content/          one Markdown file per page, with front matter (id, week, kind, title, ...)
scripts/build.py  bundles content into site/index.html (artifact) and site/standalone.html (static hosting)
scripts/template.html  the reader UI: navigation, search, progress, quizzes, diagrams, light/dark
scripts/check_links.sh  checks every URL in a file
```

## Build

```bash
uv run --no-project python scripts/build.py
open site/standalone.html
```

Check links before publishing changes:

```bash
grep -ohE '\]\(https?://[^) ]+\)' content/*.md | sed -E 's/^\]\(//; s/\)$//' | sort -u > /tmp/links.txt
bash scripts/check_links.sh /tmp/links.txt | grep -v '^200'
```

## Writing lessons

Front matter fields: `id`, `week` (0 = orientation, 1 to 6 core, 7 to 10 enterprise, 98 = under the hood, 99 = library), `kind` (`lesson`, `lab`, `page`),
`title`, `short`, `minutes`, `summary`, optional `builds`.

Special Markdown:

- ` ```mermaid ` fences render as diagrams.
- ` ```quiz ` fences hold a JSON list of `{"q", "options", "answer", "why"}` and render as a self-check.
- `> [!rule]`, `> [!warn]`, `> [!tip]`, `> [!numbers]`, `> [!interview]` render as callouts.

## License

Course text: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Code: MIT.
