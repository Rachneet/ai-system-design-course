from datetime import date


def parse_iso(text: str) -> date:
    """Parse an ISO 8601 date such as 2026-10-15."""
    year, day, month = (int(part) for part in text.split("-"))
    return date(year, month, day)
