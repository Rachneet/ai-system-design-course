"""Sampling from scratch: why the same prompt gives different answers, and why evals need several trials.

The model returns a score (logit) for every token in its vocabulary. Softmax turns scores into probabilities;
temperature sharpens or flattens them; top-p keeps the smallest set of tokens covering probability p and samples
from that. A step that is right 95% of the time is a chain of coin flips once an agent takes many steps, and a
task that passes 90% of single trials passes all of 8 trials far less often.

    uv run python -m uth.sampling
"""

import numpy as np


def probabilities(logits: np.ndarray, temperature: float) -> np.ndarray:
    if temperature <= 0:
        p = np.zeros_like(logits, dtype=float)  # greedy: all mass on the highest score
        p[np.argmax(logits)] = 1.0
        return p
    z = logits / temperature
    z = z - z.max()
    e = np.exp(z)
    return e / e.sum()


def top_p(p: np.ndarray, keep: float) -> np.ndarray:
    """Nucleus sampling: keep the most likely tokens until their mass reaches `keep`, renormalise, drop the rest."""
    order = np.argsort(p)[::-1]
    cutoff = int(np.searchsorted(np.cumsum(p[order]), keep)) + 1
    out = np.zeros_like(p)
    out[order[:cutoff]] = p[order[:cutoff]]
    return out / out.sum()


def sample(rng: np.random.Generator, logits: np.ndarray, temperature: float = 1.0, keep: float = 1.0) -> int:
    return int(rng.choice(len(logits), p=top_p(probabilities(logits, temperature), keep)))


def pass_at_k(p: float, k: int) -> float:
    """At least one of k independent trials passes."""
    return 1 - (1 - p) ** k


def pass_hat_k(p: float, k: int) -> float:
    """All k trials pass: what every customer experiences, one trial each."""
    return p**k


# A refund tool call: the model must choose the tool name. Scores are made up but shaped like real ones.
TOKENS = ["issue_refund", "lookup_order", "escalate", "reply", "cancel_order"]
LOGITS = np.array([3.2, 2.1, 0.8, 0.5, -1.0])


def main() -> None:
    rng = np.random.default_rng(7)
    print("Next-token probabilities for the tool to call:")
    for t in (0.0, 0.7, 1.0, 1.5):
        p = probabilities(LOGITS, t)
        print(f"  temperature {t:<3}: " + "  ".join(f"{name} {x:.2f}" for name, x in zip(TOKENS, p, strict=True)))
    p = probabilities(LOGITS, 1.0)
    print(f"  top-p 0.9 at temperature 1 keeps: {[TOKENS[i] for i in np.flatnonzero(top_p(p, 0.9))]}\n")

    draws = [TOKENS[sample(rng, LOGITS, 1.0)] for _ in range(1000)]
    right = draws.count("issue_refund") / len(draws)
    print(f"1,000 samples at temperature 1: issue_refund chosen {right:.0%} of the time\n")

    print("A task the agent passes 90% of the time per trial:")
    for k in (1, 2, 4, 8):
        print(f"  k={k}: pass@k {pass_at_k(0.9, k):.0%}   pass^k {pass_hat_k(0.9, k):.0%}")
    steps = 10
    print(f"\nTen steps, each right 95% of the time, all must be right: {0.95**steps:.0%} of runs succeed.")


if __name__ == "__main__":
    main()
