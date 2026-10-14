---
id: w3-regression
week: 3
kind: lesson
title: Automated regression tests for deployment
short: Regression gates
minutes: 45
summary: Turn your evals into a deployment gate, with tiered suites, thresholds that respect non-determinism, statistical comparison against a baseline, and fast feedback on every pull request.
---

## What counts as a change

In a traditional service, a deploy changes code. In an AI system, behaviour also changes when any of these change:

- Prompts (system prompt, tool descriptions, judge prompts)
- Model or model version (including a provider's alias silently moving)
- Tool code and schemas
- Retrieval: chunking, embedding model, index contents, reranker
- Guardrail thresholds
- Dependencies (an SDK upgrade that changes default parameters)

So prompts and configs must live in version control alongside code, and **every one of these changes must trigger the eval gate**, not only Python file changes.

> [!rule] If changing it can change model behaviour, it is versioned, reviewed, and evaluated like code.

## Tiered suites

Running 400 cases × 3 trials on every commit is slow and costly. Tier your suites:

| Tier | When | Size | Time | Purpose |
|---|---|---|---|---|
| Smoke | Every push | 20–30 critical cases, 1 trial | 1–3 min | Catch obvious breakage fast |
| PR gate | Every pull request touching behaviour | 150–300 cases, 3 trials | 10–20 min | Block regressions |
| Release | Before production deploy, nightly | Full suite incl. held-out, 5 trials | 30–90 min | Release confidence, trends |
| Online | Continuously in production | Sampled live traffic, judged | Ongoing | Catch drift the suite misses |

The smoke tier should include your **must-never-happen** cases: refund to the wrong customer, leaking internal documents, obeying a prompt injection. A single failure in these blocks the merge, regardless of the overall score.

## Thresholds that respect non-determinism

Agents are stochastic, so a single run of a suite is a noisy measurement. Two designs:

### Absolute thresholds per category

```yaml
gates:
  must_never:            # any failure blocks
    categories: [cross_customer_access, injection_obeyed, refund_over_limit_without_approval]
    max_failures: 0
  core:                  # pass^3 per case, aggregated
    categories: [refund_eligibility, order_status, returns_policy]
    min_pass_rate: 0.92
  quality:               # judge-graded
    categories: [tone, warranty_explanation]
    min_pass_rate: 0.85
  budgets:
    p95_latency_s: 12
    mean_tokens_per_conversation: 25000
```

### Comparison with a baseline

Absolute thresholds miss slow erosion: 94% → 93% → 92% → 91%, each change within tolerance. Also compare every PR against the current `main` baseline on the same cases, and block when the drop is statistically meaningful.

With paired results (same cases on both versions), count the cases that flipped:

- `b` = cases that passed on main and fail on the PR (regressions)
- `c` = cases that failed on main and pass on the PR (improvements)

McNemar's test asks whether `b` and `c` differ more than chance. For small counts, use the exact binomial version.

```python
from scipy.stats import binomtest

def regression_check(main: dict, pr: dict, alpha=0.05):
    b = sum(1 for k in main if main[k] and not pr[k])
    c = sum(1 for k in main if not main[k] and pr[k])
    if b + c == 0:
        return "no change", 1.0
    p = binomtest(b, b + c, 0.5, alternative="greater").pvalue
    return ("regression" if p < alpha else "ok"), p
```

> [!numbers] Your suite has 200 cases at a 92% pass rate. How big a drop can you detect? The standard error of one run's pass rate is √(0.92 × 0.08 / 200) ≈ 0.019. The difference between two independent runs has a standard error of about √2 × 0.019 ≈ 0.027, so at 95% confidence a difference smaller than about 1.96 × 0.027 ≈ **5 points** is within noise. Running 3 trials per case and using paired comparison sharpens this considerably. If you need to detect 1-point changes, you need much larger suites, which is why must-never cases use zero-tolerance gates instead.

## Make results reviewable

A gate that only says "FAILED 91.5% < 92%" is frustrating. The PR comment should show:

- Overall and per-category pass rates, with the baseline and delta.
- The list of **flipped cases** (pass → fail and fail → pass), each linking to the two traces side by side.
- Token and latency deltas.
- Judge-graded failures with the judge's reasoning.

Reviewers then read the five regressions, decide whether they are real, and either fix the change or update the case with a reason.

```text
Relay eval · suite v14 · 212 cases × 3 trials · model claude-sonnet-5-5 · prompt sha 9f3e2c1
category                  main     PR      Δ
must_never                100%    100%     0     ✅
refund_eligibility        94.1%   89.7%   -4.4   ❌ (b=7, c=1, p=0.035)
order_status              98.0%   98.4%   +0.4
tone (judge)              88.2%   90.3%   +2.1
p95 latency               9.8 s   10.4 s
tokens / convo            18.2k   21.9k   +20%   ⚠️
Regressions: refund-window-expired-017, refund-partial-022, ... (view traces)
```

## Keeping the gate fast and cheap

- **Cache what is deterministic.** Agent requests include every tool description, so almost any change invalidates them. Judge calls on identical transcripts, retrieval results, and embedding calls are often unchanged between runs, so cache those keyed by their exact inputs.
- **Run cases in parallel**, bounded by your rate limits. 200 cases × 3 trials at 20 concurrent runs of 8 s each finish in about 4 minutes.
- **Select tests by impact** for very large suites: a change to `issue_refund` must run refund cases; a change to the system prompt runs everything.
- **Use the batch API** for nightly release suites, which is typically half price and does not need to be fast.

## Pin your dependencies

A regression gate is only meaningful if the baseline is stable:

- Pin exact model IDs, not "latest" aliases.
- Pin judge model and judge prompt versions.
- Pin SDK and library versions (`uv.lock`).
- Snapshot the knowledge base used by evals, or the eval results will change whenever someone edits a policy.

## Beyond the gate: canaries and shadow tests

Evals approximate production; they never cover everything. After the gate passes:

- **Shadow**: send a copy of live traffic to the new version without showing users its output. Compare tool calls and judged quality against the current version. Safe, but write tools must be stubbed in shadow mode.
- **Canary**: route 1 to 5% of real users to the new version, watch online metrics (judge pass rates, escalation rate, thumbs-down rate, cost), and roll back automatically on regression.

Week 4 builds this into the deployment pipeline.

## Design review questions

> [!interview] Which changes trigger the eval gate? Would a change to a tool description alone trigger it?

> [!interview] What is the smallest regression your gate can reliably detect?

> [!interview] A PR fails the gate on two cases you believe are wrong. What is the process?

> [!interview] How do you know the baseline did not drift because the provider updated a model alias?

## Further reading

- [promptfoo](https://github.com/promptfoo/promptfoo), open-source eval runner with CI integration and PR comments.
- [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai), open-source eval framework with agent and sandbox support.
- [DeepEval](https://github.com/confident-ai/deepeval), pytest-style LLM tests.
- [What We Learned from a Year of Building with LLMs](https://applied-llms.org/), the evaluation and operations sections.
- [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), Anthropic.

```quiz
[
  {"q": "A teammate edits only the issue_refund tool description. Should the eval gate run?", "options": ["No, it is just documentation", "Yes; tool descriptions are part of the prompt and change behaviour", "Only the smoke tier", "Only if a Python file changed"], "answer": 1, "why": "Tool descriptions are read by the model on every call. Any behaviour-affecting artifact must trigger evaluation."},
  {"q": "Why compare against the main baseline in addition to absolute thresholds?", "options": ["Baselines are cheaper", "Absolute thresholds miss gradual erosion where each change stays above the bar", "To make PRs faster", "Thresholds are not allowed in CI"], "answer": 1, "why": "Small regressions accumulate. Paired comparison catches meaningful drops even above the threshold."},
  {"q": "What does McNemar's test use?", "options": ["Average latency", "Counts of cases that flipped from pass to fail and from fail to pass between two versions", "Token counts", "Judge reasoning"], "answer": 1, "why": "It tests whether regressions and improvements on the same cases differ by more than chance."},
  {"q": "Why do must-never cases use a zero-failure gate rather than a percentage?", "options": ["They are rare and each failure is severe; a percentage would hide a single catastrophic case", "They are easy to pass", "Percentages are not supported", "To save money"], "answer": 0, "why": "One cross-customer data leak is unacceptable no matter how good the average is."},
  {"q": "What makes a shadow deployment safe for an agent with write tools?", "options": ["Nothing; it is unsafe", "Write tools are stubbed in shadow mode so the new version cannot change real state", "Using a smaller model", "Running it at night"], "answer": 1, "why": "Shadow traffic must not act on the world. Stub or sandbox writes and compare intended actions instead."}
]
```
