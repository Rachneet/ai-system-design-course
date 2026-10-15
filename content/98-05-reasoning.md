---
id: uth-reasoning
week: 98
kind: lesson
title: "Under the hood: reasoning models and test-time compute"
short: Reasoning and test-time compute
minutes: 35
summary: Simulate voting over several samples, price the latency of reasoning tokens, and route easy questions away from expensive models, so you can decide when thinking longer is worth paying for.
---

## What this explains

Reasoning models, the ones that "think" before they answer, are better at hard problems and slower and costlier on every problem. Deciding where to use them is a system design question, not a model question: it sets your latency SLOs, your cost per resolved ticket and the shape of your gateway's routing. This page shows the mechanism, the bill, and the routing pattern that keeps most of the gain for a fraction of the cost.

## The idea: spend compute when answering, not only when training

For years the main lever for a better answer was a bigger model. **Test-time compute** spends more computation per question instead. There are two broad forms:

- **Sample several answers and combine them.** Self-consistency ([Wang et al., 2022](https://arxiv.org/abs/2203.11171)) samples several reasoning paths and takes the most common final answer. The paper reports that it improved chain-of-thought prompting by 17.9% on GSM8K, a grade-school maths benchmark.
- **Think longer in one answer.** Reasoning models write a long chain of intermediate steps before the answer. DeepSeek's R1 paper reports that such behaviour, including self-reflection and verification, can be incentivised through pure reinforcement learning, without human-labelled reasoning examples ([DeepSeek-AI, 2025](https://arxiv.org/abs/2501.12948)).

[Snell et al. (2024)](https://arxiv.org/abs/2408.03314) found that allocating test-time compute well per question is more than 4 times as efficient as plain best-of-N sampling, and that on questions where a smaller model already has some success, test-time compute can beat a 14 times larger model at the same compute. Both results come with the same condition: the gains depend on the difficulty of the question.

```viz
caption: Thinking costs the same tokens on easy and hard questions. It only pays on the hard ones, so spend it there.
<div class="vz-cols">
  <div class="vz-panel sk"><h5>Easy question</h5><div class="vz-row"><span class="ch sk g">small model</span><span class="arr sk"></span><span class="ch sk g">right, fast, cheap</span></div><div class="vz-row"><span class="ch sk w">reasoning model</span><span class="arr sk"></span><span class="ch sk b">right, 10x slower and dearer</span></div></div>
  <div class="vz-panel sk"><h5>Hard question</h5><div class="vz-row"><span class="ch sk">small model</span><span class="arr sk"></span><span class="ch sk b">often wrong</span></div><div class="vz-row"><span class="ch sk w">reasoning model</span><span class="arr sk"></span><span class="ch sk g">usually right; worth the wait</span></div></div>
</div>
```

## Run it

```bash
cd under-the-hood && uv sync
uv run python -m uth.test_time
```

Every number in this script is an input you set. The defaults are illustrations, chosen to show the shape of the trade-off, not measurements of any model.

```text
Self-consistency: each sample right 60% of the time, wrong answers spread over 4 options
   1 samples: 60% right, 1x the tokens
   3 samples: 72% right, 3x the tokens
   5 samples: 83% right, 5x the tokens
   9 samples: 94% right, 9x the tokens
  15 samples: 99% right, 15x the tokens
  Voting helps because wrong answers disagree with each other. A model that is usually wrong the same way
  gets worse: 27% right with 9 votes at 40% per sample and one wrong answer.
```

Voting works when mistakes are scattered and the right answer is the most common one. When a model is usually wrong in the same way, more votes only make it more confidently wrong. The same holds for an LLM judge sampled several times: agreement is not correctness.

```text
Reasoning tokens are output tokens (assumed: 80 tokens per second, 0.5 s to the first token)
  answer only, 300 tokens          4.2 s
  3,000 reasoning + 300 answer    41.8 s
```

Providers bill reasoning as output: OpenAI's guide says reasoning tokens "still occupy space in the model's context window and are billed as output tokens" ([reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)), and Anthropic reports thinking tokens as part of the billed output tokens ([extended thinking](https://platform.claude.com/docs/en/build-with-claude/extended-thinking)). Output is the expensive, sequential kind of token (see [attention and the KV cache](#uth-attention)), so a model that thinks for 3,000 tokens before a 300-token answer is roughly ten times slower and costlier than one that answers directly. Both providers let you set how hard the model thinks: OpenAI with a reasoning effort setting, Anthropic with an effort setting on adaptive thinking.

```text
Routing, 80% easy and 20% hard questions (assumed accuracies and relative costs):
  always small           accuracy 84.0%, cost  1.0x
  always reasoning       accuracy 94.6%, cost 20.0x
  route hard ones only   accuracy 93.0%, cost  4.8x
```

```viz
caption: With these assumptions, sending only hard questions to the reasoning model keeps most of its accuracy at a quarter of its cost. Measure your own mix before trusting the shape.
<div class="vz-bars"><span>always small</span><span class="bar sk"><i class="sk" style="--w:5%"></i></span><b>84.0%, 1x</b><span>route hard only</span><span class="bar sk"><i class="sk g" style="--w:24%"></i></span><b>93.0%, 4.8x</b><span>always reasoning</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>94.6%, 20x</b></div>
<div class="vz-src">Bars show relative cost. Assumed inputs in <code>under-the-hood/uth/test_time.py</code>: 80% easy questions; small model 95% right on easy and 40% on hard; reasoning model 97% and 85%, at 20 times the cost.</div>
```

The router's value depends entirely on how well it tells hard from easy. A router that sends hard questions to the small model gives back the accuracy; one that sends everything up gives back the savings. Measure it like any other component: an eval set labelled by difficulty, and the accuracy and cost of each route.

## What it changes in your designs

| Design decision | What test-time compute explains | Where in the course |
|---|---|---|
| Model tiers per route | Triage on a small model, hard specialist work on a reasoning model; Helpdesk OS keeps tiers in one file | [AI gateways](#w7-gateways), [capstone](#w10-capstone) |
| Latency SLOs | Thinking adds seconds to tens of seconds of decode; stream progress, or move the work to a background job | [Scaling and async](#w5-scaling) |
| Effort settings | Lower effort for routine requests is a cost and latency lever with a quality risk; measure it with your eval suite | [Caching and limits](#w5-scaling) |
| Cost per resolved ticket | Reasoning tokens are output tokens, at output prices | [AI FinOps](#w10-finops) |
| Evals | Compare tiers on the same suite, by difficulty; pass^k still applies | [Regression gates](#w3-regression) |
| Budgets and fallbacks | A budget sized for a small model empties fast when traffic moves to a reasoning model | [Monitoring](#w5-monitoring) |

> [!rule] Pay for thinking where it changes the outcome. Route by difficulty, measure the router, and keep a cheap path for the easy majority.

## Go deeper

Raschka's [*Understanding Reasoning LLMs*](https://magazine.sebastianraschka.com/p/understanding-reasoning-llms) (February 2025) is the clearest free overview of how reasoning models are built: inference-time scaling, pure reinforcement learning, supervised fine-tuning plus RL, and distillation. His second book, *Build a Reasoning Model (From Scratch)*, implements each in code in the [reasoning-from-scratch](https://github.com/rasbt/reasoning-from-scratch) repository: inference-time scaling (chapter 4), self-refinement (chapter 5), reinforcement learning with GRPO (chapters 6 and 7), and distillation (chapter 8).

```quiz
[
  {"q": "Why does self-consistency (voting over samples) help?", "options": ["More samples make each sample smarter", "Wrong answers tend to disagree with each other, so the right answer is the most common one", "It lowers the temperature", "It reduces cost"], "answer": 1, "why": "Voting amplifies whatever answer is most common. That is the right one only if mistakes are scattered."},
  {"q": "A model thinks for 3,000 tokens before a 300-token answer. How are those 3,000 tokens billed on current APIs?", "options": ["Free", "As input tokens", "As output tokens", "At a flat per-request fee"], "answer": 2, "why": "OpenAI and Anthropic both bill reasoning or thinking tokens as output tokens, the expensive and sequential kind."},
  {"q": "With 80% easy questions, what usually gives the best accuracy for the cost?", "options": ["A reasoning model for everything", "A small model for everything", "A measured router that sends only hard questions to the reasoning model", "Nine votes from the small model on everything"], "answer": 2, "why": "Thinking only pays on hard questions. A router keeps most of the gain at a fraction of the cost, if its difficulty judgement is measured."}
]
```
