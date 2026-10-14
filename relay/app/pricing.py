"""Model prices in USD per million tokens, from the provider's pricing page (checked 2026-10-14). Review on every
model change, and reconcile monthly against the invoice."""

PRICES = {  # (input, 5-minute cache write, cache read, output)
    "claude-opus-5-5": (4.00, 5.00, 0.20, 20.00),
    "claude-sonnet-5-5": (2.00, 2.50, 0.10, 10.00),
    "claude-haiku-5-5": (0.10, 0.125, 0.01, 0.50),  # prompts up to 100k tokens
}


def price(model: str) -> tuple[float, float, float, float]:
    """Prices for a model id or spec. Other providers' prices change often: set them with RELAY_PRICES (JSON),
    from the provider's pricing page, rather than trusting a table in code."""
    from .config import settings

    name = model.partition(":")[2] if ":" in model and not model.startswith("claude-") else model
    return settings.prices.get(model) or settings.prices.get(name) or PRICES.get(name, (0.0, 0.0, 0.0, 0.0))


def cost_usd(usage: dict, model: str) -> float:
    p_in, p_write, p_read, p_out = price(model)
    return (
        usage.get("input_tokens", 0) * p_in
        + usage.get("cache_creation_input_tokens", 0) * p_write
        + usage.get("cache_read_input_tokens", 0) * p_read
        + usage.get("output_tokens", 0) * p_out
    ) / 1e6
