"""Per-instance token buckets keyed by agent and tool. Like Switchboard (ADR 0002 there), exact global limits
would need shared state; per-instance buckets bound abuse at N times the limit across N instances."""

import time


class Buckets:
    def __init__(self, per_minute: int, clock=time.monotonic):
        self.rate, self.capacity, self.clock = per_minute / 60.0, float(per_minute), clock
        self.state: dict[str, tuple[float, float]] = {}

    def take(self, key: str) -> float:
        """Returns 0 when allowed, otherwise the seconds to wait."""
        now = self.clock()
        tokens, last = self.state.get(key, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.rate)
        if tokens >= 1:
            self.state[key] = (tokens - 1, now)
            return 0.0
        self.state[key] = (tokens, now)
        return (1 - tokens) / self.rate
