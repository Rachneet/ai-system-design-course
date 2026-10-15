def apply_discount(price_cents: int, percent: int) -> int:
    """Price after a percentage discount, in cents."""
    return price_cents - price_cents * percent // 100
