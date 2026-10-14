# AI System Design Course

A free, six-week course on designing production AI systems: agents, retrieval, evals, security,
deployment, and observability, taught through one application (Relay, a support agent) that grows
from a prototype into a monitored cloud service.

- 6 weeks, 24 lessons, 5 labs, a capstone, 8 design drills, a glossary, and a reading list
- Every lesson has worked numbers, diagrams, design review questions, and a self-check quiz
- Every linked resource is free (links checked on 2026-10-14)

This is an independent, original course. Its weekly topics follow the public syllabus of paid AI
system design cohorts so that students can study the same ground for free. No paid course material
is reproduced.

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

Front matter fields: `id`, `week` (0 = orientation, 1-6, 7 = library), `kind` (`lesson`, `lab`, `page`),
`title`, `short`, `minutes`, `summary`, optional `builds`.

Special Markdown:

- ` ```mermaid ` fences render as diagrams.
- ` ```quiz ` fences hold a JSON list of `{"q", "options", "answer", "why"}` and render as a self-check.
- `> [!rule]`, `> [!warn]`, `> [!tip]`, `> [!numbers]`, `> [!interview]` render as callouts.

## License

Course text: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Code: MIT.
