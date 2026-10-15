"""Test-time compute from scratch: buying accuracy with more tokens at answer time, and when it is worth it.

Two ways to spend more compute per question: sample several answers and take the most common one (self-consistency),
or let the model write a long chain of reasoning before answering (reasoning or "thinking" models). Both raise
accuracy on hard questions and multiply tokens, cost and latency on every question. Routing spends them only where
they pay. Every number below is an input you choose; replace them with your own measurements.

    uv run python -m uth.test_time
"""

from collections import Counter

import numpy as np


def vote_accuracy(p: float, n: int, wrong_answers: int, trials: int = 20_000, seed: int = 0) -> float:
    """Simulate n samples per question: right with probability p, otherwise one of `wrong_answers` wrong answers
    picked uniformly. The most common answer wins (ties broken at random). Returns the share of questions right."""
    rng = np.random.default_rng(seed)
    right = 0
    for _ in range(trials):
        answers = np.where(rng.random(n) < p, 0, rng.integers(1, wrong_answers + 1, n))
        counts = Counter(answers.tolist()).most_common()
        top = [a for a, c in counts if c == counts[0][1]]
        right += rng.choice(top) == 0
    return right / trials


def seconds(output_tokens: int, tokens_per_second: float, first_token_s: float) -> float:
    return first_token_s + output_tokens / tokens_per_second


def route(mix: dict[str, float], policy: dict[str, str], models: dict[str, dict]) -> tuple[float, float]:
    """Expected accuracy and cost per question when each kind of question goes to the model the policy names."""
    acc = sum(share * models[policy[kind]]["acc"][kind] for kind, share in mix.items())
    cost = sum(share * models[policy[kind]]["cost"] for kind, share in mix.items())
    return acc, cost


def main() -> None:
    print("Self-consistency: each sample right 60% of the time, wrong answers spread over 4 options")
    for n in (1, 3, 5, 9, 15):
        print(f"  {n:>2} samples: {vote_accuracy(0.6, n, 4):.0%} right, {n}x the tokens")
    print("  Voting helps because wrong answers disagree with each other. A model that is usually wrong the same way")
    print(f"  gets worse: {vote_accuracy(0.4, 9, 1):.0%} right with 9 votes at 40% per sample and one wrong answer.\n")

    print("Reasoning tokens are output tokens (assumed: 80 tokens per second, 0.5 s to the first token)")
    for label, tokens in (("answer only, 300 tokens", 300), ("3,000 reasoning + 300 answer", 3300)):
        print(f"  {label:<30} {seconds(tokens, 80, 0.5):5.1f} s")
    print()

    models = {  # assumptions for illustration: accuracy per kind of question, relative cost per question
        "small": {"acc": {"easy": 0.95, "hard": 0.40}, "cost": 1.0},
        "reasoning": {"acc": {"easy": 0.97, "hard": 0.85}, "cost": 20.0},
    }
    mix = {"easy": 0.8, "hard": 0.2}
    print("Routing, 80% easy and 20% hard questions (assumed accuracies and relative costs):")
    for name, policy in (
        ("always small", {"easy": "small", "hard": "small"}),
        ("always reasoning", {"easy": "reasoning", "hard": "reasoning"}),
        ("route hard ones only", {"easy": "small", "hard": "reasoning"}),
    ):
        acc, cost = route(mix, policy, models)
        print(f"  {name:<22} accuracy {acc:.1%}, cost {cost:4.1f}x")
    print("  The router keeps most of the accuracy for a quarter of the cost, if it can tell hard from easy.")


if __name__ == "__main__":
    main()
