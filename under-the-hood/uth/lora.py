"""LoRA from scratch: adapt a frozen model with a small low-rank update, and serve many adapters on one base.

A layer computes y = x W. Full fine-tuning changes all of W (d_in x d_out numbers). LoRA freezes W and learns
y = x W + (alpha / r) x A B, with A (d_in x r) and B (r x d_out), r small. B starts at zero, so training starts from
the base model exactly. Afterwards the update can be merged into W, or kept apart so one base serves many tenants,
each with its own small adapter.

    uv run python -m uth.lora
"""

import numpy as np


class LoRALinear:
    def __init__(self, w: np.ndarray, r: int, alpha: float, rng: np.random.Generator):
        self.w = w  # frozen
        self.a = rng.normal(0, 1 / np.sqrt(w.shape[0]), (w.shape[0], r))
        self.b = np.zeros((r, w.shape[1]))  # zero: the adapter starts as a no-op
        self.scale = alpha / r

    def __call__(self, x: np.ndarray) -> np.ndarray:
        return x @ self.w + self.scale * (x @ self.a) @ self.b

    def merged(self) -> np.ndarray:
        return self.w + self.scale * self.a @ self.b

    def trainable(self) -> int:
        return self.a.size + self.b.size

    def train(self, x: np.ndarray, y: np.ndarray, steps: int = 300, lr: float = 10.0) -> list[float]:
        """Plain gradient descent on mean squared error, updating only A and B."""
        losses = []
        for _ in range(steps):
            err = self(x) - y
            losses.append(float((err**2).mean()))
            g = 2 * err / err.size  # dLoss/dOutput for the mean over every output
            xa = x @ self.a
            grad_b = self.scale * xa.T @ g
            grad_a = self.scale * x.T @ (g @ self.b.T)
            self.b -= lr * grad_b
            self.a -= lr * grad_a
        return losses


def task(rng: np.random.Generator, w: np.ndarray, rank: int, n: int = 512):
    """A tenant's data: the base behaviour plus a low-rank shift the base model does not know."""
    d_in, d_out = w.shape
    shift = rng.normal(0, 1, (d_in, rank)) @ rng.normal(0, 1, (rank, d_out)) / d_in
    x = rng.normal(0, 1, (n, d_in))
    return x, x @ (w + shift)


def main() -> None:
    rng = np.random.default_rng(0)
    d = 256
    w = rng.normal(0, 1 / np.sqrt(d), (d, d))
    full = w.size
    print(f"Layer {d} x {d}: full fine-tuning trains {full:,} numbers.")
    for r in (4, 8, 16):
        print(f"  LoRA rank {r:>2}: {2 * d * r:>7,} trainable ({2 * d * r / full:.1%} of the layer)")

    adapters, data = {}, {}
    for tenant in ("acme", "globex"):
        x, y = data[tenant] = task(rng, w, rank=4)
        layer = LoRALinear(w, r=8, alpha=16, rng=rng)
        base_loss = float(((x @ w - y) ** 2).mean())
        losses = layer.train(x, y)
        adapters[tenant] = layer
        print(f"\n{tenant}: base model error {base_loss:.4f}; after LoRA training {losses[-1]:.4f}")
    gx, gy = data["globex"]
    wrong = float(((adapters["acme"](gx) - gy) ** 2).mean())
    print(f"acme's adapter on globex's data: error {wrong:.4f}. An adapter carries its tenant's behaviour.")
    x = rng.normal(0, 1, (4, d))
    a = adapters["acme"]
    print(f"\nMerged weights give the same output as base + adapter: {np.allclose(a(x), x @ a.merged())}")
    print(f"Base weights untouched by training: {np.array_equal(a.w, w)}")
    print(f"One base ({full:,} numbers) serves both tenants; each adapter adds {a.trainable():,}.")
    print("At serving time the request names its adapter, so the gateway must decide which a caller may name.")


if __name__ == "__main__":
    main()
