---
id: w3-judge
week: 3
kind: lesson
title: LLM-as-judge versus human evaluation
short: LLM judge vs humans
minutes: 50
summary: When to use a model as a grader, how to design judges that agree with humans, how to measure that agreement, and the biases that make naive judges unreliable.
---

## Why judges exist

Code checks answer "did it call `issue_refund` with $45?". They cannot answer "was the explanation of the warranty process correct and kind?". Humans can, but humans are slow, expensive, and inconsistent at scale. An **LLM judge** is a model prompted to grade an output against criteria. Done well, it gives you near-human judgement on thousands of cases per hour for a few dollars.

Done badly, it gives you confident numbers that mean nothing. The difference is calibration against human labels.

> [!rule] A judge is a classifier. Before you trust its scores, measure its agreement with human labels on your data, just as you would for any other model.

## Human evaluation: the reference

Humans define what "good" means. Use them for:

- **Labelling a calibration set** that judges are measured against.
- **Error analysis** (previous lesson): reading traces to find failure modes.
- **High-stakes release decisions** and anything legally sensitive.
- **Spot-checking** judge outputs in production.

Make human labels useful:

- **Use a domain expert**, ideally one "benevolent dictator" whose judgement defines quality for the product, rather than averaging many non-experts.
- **Binary pass/fail with a written reason** beats 1 to 5 Likert scores. Raters disagree on whether something is a 3 or a 4; they agree far more on pass or fail, and the reason is what you learn from.
- **Write a labelling guide** with examples of pass and fail at the boundary.
- **Measure inter-rater agreement** when you have more than one rater. If two humans agree only 70% of the time, no judge will exceed that, and your criteria need work.

Shreya Shankar's [Who Validates the Validators?](https://arxiv.org/abs/2404.12272) shows a subtle point: people refine their criteria while grading. Expect your rubric to change after the first 50 labels. That is normal and good.

## Designing a judge

### One criterion per judge

A judge that scores "accuracy, helpfulness, tone, and safety" in one call produces muddled scores. Build one judge per failure mode that matters, each with a binary verdict:

- `cites_correct_policy`: does the reply state the return window that matches the cited policy?
- `no_unauthorised_promise`: does the reply promise anything (refund, discount, delivery date) not supported by tool results?
- `warranty_route_offered`: when a return is ineligible due to a defect, is the warranty path explained?

### Give the judge what it needs

A judge needs the same context a human grader would: the conversation, the tool calls and results, the retrieved documents, and the rubric. Judging "is this answer correct?" without the source documents just asks the judge to guess.

### Ask for reasoning, then a verdict, in structured output

```python
from typing import Literal
from openai import OpenAI
from pydantic import BaseModel, ConfigDict

class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")   # strict schemas need additionalProperties: false
    reasoning: str                      # short; written before the verdict
    verdict: Literal["pass", "fail"]

JUDGE_PROMPT = """You are grading one reply from a customer support agent for an outdoor gear store.

Criterion: The reply must not promise anything (refund, replacement, discount, delivery date)
unless the tool results in the transcript support it.

Pass example: Tool shows refund issued for $45; reply says "I've refunded $45."
Fail example: No refund tool call; reply says "You'll get your refund in 3 days."
Fail example: Tool shows ETA Oct 18; reply says "It will arrive tomorrow."

<transcript>
{transcript}
</transcript>

Explain your reasoning in two or three sentences, then give the verdict."""

# One client for OpenAI, Gemini, OpenRouter, Hugging Face, vLLM or Ollama: change base_url and model.
client = OpenAI(base_url=JUDGE_BASE_URL, api_key=JUDGE_API_KEY)

def judge(transcript: str) -> Verdict:
    resp = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[{"role": "user", "content": JUDGE_PROMPT.format(transcript=transcript)}],
        response_format={"type": "json_schema", "json_schema": {
            "name": "verdict", "schema": Verdict.model_json_schema(), "strict": True}},
    )
    return Verdict.model_validate_json(resp.choices[0].message.content)
```

JSON-schema output is supported by [OpenAI](https://developers.openai.com/api/docs/guides/structured-outputs), Gemini's [OpenAI-compatible endpoint](https://ai.google.dev/gemini-api/docs/openai), [vLLM](https://docs.vllm.ai/en/latest/features/structured_outputs.html), [Ollama](https://docs.ollama.com/capabilities/structured-outputs) (local models) and [OpenRouter](https://openrouter.ai/docs/features/structured-outputs) (on endpoints that support it). Anthropic's SDK does the same natively with `client.messages.parse(..., output_format=Verdict)` and returns `parsed_output` ([docs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)). Whatever the provider, validate the result: a judge that returns malformed JSON should count as an error, not a pass.

### Pick the judge model deliberately

A judge should usually be at least as capable as the model being judged on the relevant skill. For narrow binary checks, a small model with a good prompt often matches a large one: measure it. Pin the judge model version; a silent judge upgrade changes all your scores.

Prefer a judge from a **different model family** than the agent. Models can recognise their own outputs, and the more strongly they do, the more they favour them ([Panickssery et al., 2024](https://arxiv.org/abs/2404.13076)). Because the judge is just another model call, it can sit on any provider: an agent on OpenAI judged by Gemini, an agent on Claude judged by an open Qwen or Llama model on vLLM. In Relay this is one setting, for example `RELAY_MODEL=openai:gpt-5` with `RELAY_JUDGE_MODEL=gemini:gemini-2.5-flash`.

```viz
caption: Same family grading itself can inflate scores. A judge from another family, calibrated on human labels, is the safer default.
<div class="vz-cols">
  <div class="vz-panel sk b"><h5>Same family</h5>
    <div class="vz-row"><span class="ch sk">agent: family A</span><span class="arr sk"></span><span class="ch sk b">judge: family A</span></div>
    <p>recognises its own style, favours it</p>
  </div>
  <div class="vz-panel sk g"><h5>Different family</h5>
    <div class="vz-row"><span class="ch sk">agent: family A</span><span class="arr sk"></span><span class="ch sk g">judge: family B</span></div>
    <p>still calibrate it against human labels</p>
  </div>
</div>
<div class="vz-src">Self-preference: Panickssery, Bowman and Feng, <a href="https://arxiv.org/abs/2404.13076">LLM Evaluators Recognize and Favor Their Own Generations</a> (2024).</div>
```

## Measuring judge quality

Label 100 to 200 examples by hand (pass/fail), balanced so there are enough fails. Split into a development set (to tune the judge prompt) and a test set (to report final agreement).

Do not report raw accuracy alone. If 90% of outputs pass, a judge that always says "pass" is 90% accurate and useless. Report:

| Metric | Meaning |
|---|---|
| True positive rate (recall on fails) | Of real failures, how many did the judge catch? |
| True negative rate | Of real passes, how many did it pass? |
| Cohen's kappa | Agreement corrected for chance. The common [Landis and Koch (1977)](https://doi.org/10.2307/2529310) bands call 0.61 to 0.80 substantial and above 0.80 almost perfect; they are a convention, not a law |

```viz
caption: 100 labelled outputs, 10 of them real failures. The judge that passes everything scores 90% accuracy and catches nothing; kappa and fail recall expose it.
<div class="vz-cols">
  <div class="vz-panel sk b"><h5>Always says pass</h5>
    <div class="vz-bars"><span>accuracy</span><span class="bar sk"><i class="sk c" style="--w:90%"></i></span><b>0.90</b><span>fail recall</span><span class="bar sk"><i class="sk b" style="--w:1%"></i></span><b>0.00</b><span>kappa</span><span class="bar sk"><i class="sk b" style="--w:1%"></i></span><b>0.00</b></div>
  </div>
  <div class="vz-panel sk g"><h5>Catches 8 of 10 fails</h5>
    <div class="vz-bars"><span>accuracy</span><span class="bar sk"><i class="sk c" style="--w:94%"></i></span><b>0.94</b><span>fail recall</span><span class="bar sk"><i class="sk g" style="--w:80%"></i></span><b>0.80</b><span>kappa</span><span class="bar sk"><i class="sk g" style="--w:69%"></i></span><b>0.69</b></div>
    <p>4 false alarms on real passes</p>
  </div>
</div>
<p>accuracy barely moves; kappa goes from 0 to 0.69</p>
```

```python
from sklearn.metrics import cohen_kappa_score, confusion_matrix

human = [...]  # "pass"/"fail" labels
model = [judge(t).verdict for t in transcripts]
tn, fp, fn, tp = confusion_matrix(human, model, labels=["pass", "fail"]).ravel()
print("fail recall:", tp / (tp + fn), " pass recall:", tn / (tn + fp))
print("kappa:", cohen_kappa_score(human, model))
```

### Correcting for judge error

If you know the judge's error rates, you can estimate the true pass rate from the judged pass rate. With true positive rate on passes `p_pass` and true negative rate on fails `p_fail`:

`true_pass_rate ≈ (judged_pass_rate + p_fail − 1) / (p_pass + p_fail − 1)`

> [!numbers] The judge passes 85% of outputs. On the test set it correctly passes 95% of real passes and correctly fails 90% of real fails. Estimated true pass rate = (0.85 + 0.90 − 1) / (0.95 + 0.90 − 1) = 0.75 / 0.85 ≈ **0.88**. Small here, but when a judge is lenient the correction can move results by 10 points or more.

## Known judge biases

[Judging LLM-as-a-Judge](https://arxiv.org/abs/2306.05685) found that strong judges agreed with human preferences over 80% of the time, about the same rate at which humans agree with each other. It also documented position, verbosity, and self-enhancement biases and limited reasoning ability:

| Bias | What happens | Mitigation |
|---|---|---|
| Position bias | In pairwise comparisons, prefers the first (or second) option | Evaluate both orders; count only consistent wins |
| Verbosity bias | Prefers longer answers | Rubric that rewards concision; binary criteria |
| Self-preference | Prefers outputs from its own model family ([Panickssery et al.](https://arxiv.org/abs/2404.13076)) | Use a different family as judge where possible; calibrate |
| Leniency | Passes borderline cases | Include hard fail examples in the prompt; measure fail recall |
| Rubric drift | Interprets vague criteria differently over time | Specific, example-backed criteria; pinned model version |

## Pairwise versus pointwise

- **Pointwise** (grade one output against a rubric): best for regression testing and monitoring. Stable and easy to aggregate.
- **Pairwise** (which of two outputs is better?): best for comparing two prompts or models when quality is hard to define absolutely. Humans and models are both better at relative judgements. Always swap positions.

## When to use what

| Situation | Use |
|---|---|
| Tool called with right args, end state correct | Code |
| Format, length, citation IDs present | Code |
| Factual consistency with sources | Judge, calibrated |
| Tone, empathy, policy explanation quality | Judge, calibrated, with human spot checks |
| New product area, criteria not yet clear | Humans first; build judges after |
| Release decision on a high-risk change | Judge on full suite + human review of a sample of diffs |

## Cost

400 cases × 3 trials × 3 judges = 3,600 judge calls per full run. At about 4,000 input and 150 output tokens each, the cost is 3,600 × (4,000 × input price + 150 × output price) / 1M:

```viz
caption: The same 3,600 judge calls cost from under $2 to about $34 depending on the model. If a small judge's kappa is close to a large one's, use it for CI and the large one for release checks.
<div class="vz-bars"><span>Claude Sonnet 5.5</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>$34</b><span>GPT-5</span><span class="bar sk"><i class="sk w" style="--w:68%"></i></span><b>$23</b><span>Gemini 2.5 Flash</span><span class="bar sk"><i class="sk w" style="--w:17%"></i></span><b>$5.70</b><span>GPT-5 mini</span><span class="bar sk"><i class="sk w" style="--w:14%"></i></span><b>$4.70</b><span>Claude Haiku 5.5</span><span class="bar sk"><i class="sk w" style="--w:5%"></i></span><b>$1.70</b><span>Gemini 2.5 Flash-Lite</span><span class="bar sk"><i class="sk w" style="--w:5%"></i></span><b>$1.70</b></div>
<p>open models on your own GPUs: no per-token bill, you pay for GPU hours</p>
<div class="vz-src">List prices per million input / output tokens in October 2026: Sonnet 5.5 $2 / $10 and Haiku 5.5 $0.10 / $0.50 (<a href="https://platform.claude.com/docs/en/about-claude/pricing">Anthropic</a>); GPT-5 $1.25 / $10 and GPT-5 mini $0.25 / $2 (<a href="https://developers.openai.com/api/docs/pricing">OpenAI</a>); 2.5 Flash $0.30 / $2.50 and 2.5 Flash-Lite $0.10 / $0.40 (<a href="https://ai.google.dev/gemini-api/docs/pricing">Google</a>). Same token counts assumed for every model; real tokenizers differ, so the same text can be more or fewer tokens.</div>
```

## Design review questions

> [!interview] What is your judge's kappa against human labels, and on how many examples?

> [!interview] Your pass rate went up 6 points after a prompt change. How do you know the judge did not just get more lenient on the new style?

> [!interview] Who is the domain expert whose labels define "correct" here?

## Further reading

- [Creating a LLM-as-a-Judge That Drives Business Results](https://hamel.dev/blog/posts/llm-judge/), Hamel Husain. The critique-shadowing method.
- [Evaluating the Effectiveness of LLM-Evaluators](https://eugeneyan.com/writing/llm-evaluators/), Eugene Yan. A survey of what works.
- [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685), biases measured.
- [Who Validates the Validators?](https://arxiv.org/abs/2404.12272), Shankar et al., on criteria drift.
- [RAGAS](https://docs.ragas.io/) for ready-made RAG metrics like faithfulness, to calibrate like any other judge.

```quiz
[
  {"q": "90% of your outputs are good. A judge scores 90% accuracy against human labels. What should you check?", "options": ["Nothing, 90% is good", "Its recall on actual failures; it may just pass everything", "Its latency", "Its token count"], "answer": 1, "why": "With imbalanced data, a judge that always says pass gets 90% accuracy and catches zero failures. Look at per-class rates and kappa."},
  {"q": "Why prefer binary pass/fail over 1-to-5 scores?", "options": ["Fewer tokens", "Higher agreement between raters and clearer, actionable outcomes", "Models cannot output numbers", "Easier to chart"], "answer": 1, "why": "Graders rarely agree on the difference between a 3 and a 4. A binary verdict with a reason is more consistent and tells you what to fix."},
  {"q": "In a pairwise comparison, how do you control for position bias?", "options": ["Always put your new model first", "Run both orders and count only consistent preferences", "Use a smaller judge", "Use temperature 0"], "answer": 1, "why": "Swapping positions and requiring agreement removes the effect of order."},
  {"q": "What is the most important input to a groundedness judge besides the answer?", "options": ["The user's name", "The retrieved source documents the answer should be based on", "The model's temperature", "Previous judge scores"], "answer": 1, "why": "Without the sources, the judge can only guess whether claims are supported."}
]
```
