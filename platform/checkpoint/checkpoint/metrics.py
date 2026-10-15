from prometheus_client import Counter, Histogram

decisions = Counter("checkpoint_decisions_total", "Policy decisions", ["action", "decision"])
upstream_seconds = Histogram("checkpoint_upstream_seconds", "Upstream tool call latency", ["server"])
flags = Counter("checkpoint_output_flags_total", "Tool output findings", ["flag"])
