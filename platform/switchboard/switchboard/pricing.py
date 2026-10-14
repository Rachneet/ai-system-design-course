"""USD per million tokens, from the provider's pricing page (checked 2026-10-14). Review on every model change."""

from decimal import Decimal

PRICES = {  # (input, 5-minute cache write, cache read, output)
    "claude-opus-5-5": (4.00, 5.00, 0.20, 20.00),
    "claude-sonnet-5-5": (2.00, 2.50, 0.10, 10.00),
    "claude-haiku-5-5": (0.10, 0.125, 0.01, 0.50),
}


def known(model: str) -> bool:
    return model in PRICES


def cost_usd(model: str, usage: dict) -> Decimal:
    p_in, p_write, p_read, p_out = PRICES.get(model, (0.0, 0.0, 0.0, 0.0))
    micro = (
        usage.get("input_tokens", 0) * p_in
        + usage.get("cache_creation_input_tokens", 0) * p_write
        + usage.get("cache_read_input_tokens", 0) * p_read
        + usage.get("output_tokens", 0) * p_out
    )
    return Decimal(str(micro)) / Decimal(1_000_000)
