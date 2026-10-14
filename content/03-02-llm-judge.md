---
id: w3-judge
week: 3
kind: lesson
title: LLM-as-judge versus human evaluation
short: LLM judge vs humans
minutes: 45
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
- **Binary pass/fail with a written reason** beats 1–5 Likert scores. Raters disagree on whether something is a 3 or a 4; they agree far more on pass or fail, and the reason is what you learn from.
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
from pydantic import BaseModel
from typing import Literal

class Verdict(BaseModel):
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

def judge(transcript: str) -> Verdict:
    resp = client.messages.parse(
        model=JUDGE_MODEL, max_tokens=512,
        messages=[{"role": "user", "content": JUDGE_PROMPT.format(transcript=transcript)}],
        output_format=Verdict,
    )
    return resp.parsed_output
```

### Pick the judge model deliberately

A judge should usually be at least as capable as the model being judged on the relevant skill. For narrow binary checks, a small model with a good prompt often matches a large one: measure it. Pin the judge model version; a silent judge upgrade changes all your scores.

## Measuring judge quality

Label 100 to 200 examples by hand (pass/fail), balanced so there are enough fails. Split into a development set (to tune the judge prompt) and a test set (to report final agreement).

Do not report raw accuracy alone. If 90% of outputs pass, a judge that always says "pass" is 90% accurate and useless. Report:

| Metric | Meaning |
|---|---|
| True positive rate (recall on fails) | Of real failures, how many did the judge catch? |
| True negative rate | Of real passes, how many did it pass? |
| Cohen's kappa | Agreement corrected for chance; above 0.6 is good, above 0.8 is excellent |

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

Studies such as [Judging LLM-as-a-Judge](https://arxiv.org/abs/2306.05685) document systematic biases:

| Bias | What happens | Mitigation |
|---|---|---|
| Position bias | In pairwise comparisons, prefers the first (or second) option | Evaluate both orders; count only consistent wins |
| Verbosity bias | Prefers longer answers | Rubric that rewards concision; binary criteria |
| Self-preference | Prefers outputs from its own model family | Use a different family as judge where possible; calibrate |
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

> [!numbers] 400 cases × 3 trials × 3 judges = 3,600 judge calls. At about 4,000 input and 150 output tokens each on Sonnet 5.5 ($2 / $10 per million): 3,600 × (4,000 × 2 + 150 × 10) / 1e6 ≈ **$34** per full run. On Haiku 5.5 ($0.10 / $0.50): about **$1.70**. If the small judge's kappa is close to the large one's, use it for CI and the large one for release checks.

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
