---
id: uth-sampling
week: 98
kind: lesson
title: "Under the hood: sampling, temperature and why evals need trials"
short: Sampling from scratch
minutes: 30
summary: Turn a model's scores into a choice with temperature and top-p, and see why the same prompt gives different answers, why temperature 0 is not a guarantee, and why agents are gated on pass^k.
---

## What this explains

In Week 3 you gate agents on **pass^k**, the chance that all k trials pass, and not on a single run ([regression gates](#w3-regression)). This page shows where the randomness comes from, so the rule stops being a rule and becomes arithmetic. It also explains two things teams get wrong: that temperature 0 makes a model deterministic, and that a step that is right 95% of the time is safe to chain.

## The idea: scores, then a weighted dice roll

At each step the model outputs a score, a logit, for every token in its vocabulary. Softmax turns the scores into probabilities that add up to 1. Then the server picks one token:

- **Temperature** divides the scores before softmax. Below 1 it sharpens the distribution towards the top token; above 1 it flattens it. Temperature 0 is treated as "always take the top token" (greedy decoding).
- **Top-p** (nucleus sampling, from [Holtzman et al.](https://arxiv.org/abs/1904.09751)) keeps the smallest set of tokens whose probabilities add up to p, drops the rest, and samples from what is left. It removes the long tail of unlikely tokens without fixing how many survive.

```viz
caption: The same five scores at three temperatures. Lower temperature concentrates probability on the top choice; it never changes which choice is on top.
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk"><h5>temperature 0.7</h5><div class="vz-bars"><span>issue_refund</span><span class="bar sk"><i class="sk g" style="--w:79%"></i></span><b>0.79</b><span>lookup_order</span><span class="bar sk"><i class="sk" style="--w:16%"></i></span><b>0.16</b><span>escalate</span><span class="bar sk"><i class="sk" style="--w:3%"></i></span><b>0.03</b></div></div>
  <div class="vz-panel sk"><h5>temperature 1.0</h5><div class="vz-bars"><span>issue_refund</span><span class="bar sk"><i class="sk g" style="--w:66%"></i></span><b>0.66</b><span>lookup_order</span><span class="bar sk"><i class="sk" style="--w:22%"></i></span><b>0.22</b><span>escalate</span><span class="bar sk"><i class="sk" style="--w:6%"></i></span><b>0.06</b></div></div>
  <div class="vz-panel sk"><h5>temperature 1.5</h5><div class="vz-bars"><span>issue_refund</span><span class="bar sk"><i class="sk w" style="--w:52%"></i></span><b>0.52</b><span>lookup_order</span><span class="bar sk"><i class="sk" style="--w:25%"></i></span><b>0.25</b><span>escalate</span><span class="bar sk"><i class="sk" style="--w:11%"></i></span><b>0.11</b></div></div>
</div>
<div class="vz-src">Output of <code>uv run python -m uth.sampling</code>; the scores are illustrative, shaped like a model choosing which tool to call.</div>
```

## Run it

```bash
cd under-the-hood && uv sync
uv run python -m uth.sampling
```

```text
1,000 samples at temperature 1: issue_refund chosen 67% of the time

A task the agent passes 90% of the time per trial:
  k=1: pass@k 90%   pass^k 90%
  k=2: pass@k 99%   pass^k 81%
  k=4: pass@k 100%   pass^k 66%
  k=8: pass@k 100%   pass^k 43%

Ten steps, each right 95% of the time, all must be right: 60% of runs succeed.
```

Two lessons in those numbers:

- **pass@k flatters, pass^k tells the truth.** If you may pick the best of 8 tries, a 90% agent looks perfect. Each customer gets one try, and over 8 customers there is only a 43% chance that none of them saw a failure. That is why gates use pass^k.
- **Steps multiply.** An agent that picks the right tool 95% of the time and takes ten steps finishes cleanly in only 60% of runs, if each step is an independent draw. Fewer steps, deterministic code where a choice does not need a model, and validation after risky steps all raise the product.

```viz
caption: A 90% agent judged by its best try looks perfect. Judged by what every customer gets, it fails often. Gate on pass^k.
<div class="vz-bars"><span>pass@8 (best of 8)</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>100%</b><span>pass^1</span><span class="bar sk"><i class="sk" style="--w:90%"></i></span><b>90%</b><span>pass^8 (all 8 pass)</span><span class="bar sk"><i class="sk b" style="--w:43%"></i></span><b>43%</b></div>
<div class="vz-src">1 - 0.1<sup>8</sup> and 0.9<sup>8</sup>, assuming independent trials; <a href="https://arxiv.org/abs/2406.12045">τ-bench</a> introduced pass^k for agents.</div>
```

## Temperature 0 is not a determinism switch

Setting temperature 0 removes the dice roll, but the scores themselves can differ slightly between two runs of the same prompt on a busy server. Thinking Machines traced the main cause in [*Defeating Nondeterminism in LLM Inference*](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/) (September 2025): the server's load changes the batch size of each forward pass, and kernels that are not batch-invariant add numbers in a different order at different batch sizes, so rounding differs. When two tokens are nearly tied, a tiny difference flips the choice, and the rest of the answer follows a different path. Some providers also restrict or ignore sampling settings on reasoning models.

> [!rule] Never assume one run is the run. Evaluate with several trials, gate on pass^k, make the checks that must hold deterministic (schemas, policy, tool arguments), and record the model version and settings with every eval result.

## What it changes in your designs

| Design decision | What sampling explains | Where in the course |
|---|---|---|
| Evals with trials and pass^k | Every run is a draw; one passing run proves little | [Regression gates](#w3-regression), [eval datasets](#w3-datasets) |
| Temperature per job | Extraction, routing and judging want low temperature; brainstorming and drafting can use more | [LLM judges](#w3-judge) |
| Fewer, safer steps | Per-step reliability multiplies across an agent's steps | [Agent design](#w1-agents) |
| Validation and retries | A schema check plus one retry turns a 95% step into about 99.75%, if failures are independent | [Guardrails](#w2-guardrails) |
| Reproducing a bug | Store prompt, model version, settings and the response; exact replay is not guaranteed | [Tracing](#w5-tracing) |

## Go deeper

Raschka's book covers decoding in chapter 5, "Pretraining on Unlabeled Data", including temperature scaling and top-k sampling ([chapter 5 code](https://github.com/rasbt/LLMs-from-scratch/tree/main/ch05)). His second book, [*Build a Reasoning Model (From Scratch)*](https://github.com/rasbt/reasoning-from-scratch), starts with generating text from a pre-trained model (chapter 2) and evaluating it (chapter 3), useful next steps once you have built the basics.

```quiz
[
  {"q": "Lowering the temperature from 1.0 to 0.7 does what?", "options": ["Changes which token has the highest score", "Concentrates probability on the higher-scoring tokens without changing their order", "Makes the model smarter", "Removes the KV cache"], "answer": 1, "why": "Temperature rescales the scores before softmax. The ranking stays the same; the distribution gets sharper."},
  {"q": "An agent passes a task in 90% of single trials. What share of 8 independent trials all pass?", "options": ["90%", "About 72%", "About 43%", "About 10%"], "answer": 2, "why": "0.9 to the power 8 is about 0.43. Every customer gets one trial, so this is the number that matters."},
  {"q": "Two calls with the same prompt at temperature 0 return different answers. What is the most likely cause on a shared inference server?", "options": ["A bug in your code", "Varying batch sizes change the order of floating-point additions, shifting scores enough to flip near-tied tokens", "The provider ignores temperature", "The KV cache was cleared"], "answer": 1, "why": "Thinking Machines showed that load-dependent batch size, with kernels that are not batch-invariant, is the main cause."}
]
```
