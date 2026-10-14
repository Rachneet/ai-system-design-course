"""Detect and optionally redact personal data in request text before it leaves the company."""

import re

CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Phone numbers need phone-like separators, so plain digit IDs (order numbers, SKUs) are left alone.
PHONE = re.compile(r"(?<![\w+])(?:\+\d{1,3}[ .-]?)?(?:\(\d{2,4}\)[ .-]?|\d{2,4}[ .-])\d{3,4}[ .-]\d{3,4}(?!\w)")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}\b")


def luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for d in reversed(digits):
        n = int(d)
        if alt:
            n = n * 2 - 9 if n * 2 > 9 else n * 2
        total += n
        alt = not alt
    return total % 10 == 0


def scrub(text: str) -> tuple[str, int]:
    """Returns (redacted text, number of findings). Card numbers must pass the Luhn check."""
    found = 0

    def card(m: re.Match) -> str:
        nonlocal found
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            found += 1
            return "[CARD]"
        return m.group()

    def tag(label: str):
        def sub(_: re.Match) -> str:
            nonlocal found
            found += 1
            return f"[{label}]"

        return sub

    text = CARD.sub(card, text)
    text = IBAN.sub(tag("IBAN"), text)
    text = EMAIL.sub(tag("EMAIL"), text)
    text = PHONE.sub(tag("PHONE"), text)
    return text, found


def scrub_request(body: dict) -> tuple[dict, int]:
    """Scrub every text field the model will read: system prompt and message text blocks (incl. tool results)."""
    total = 0

    def fix(value):
        nonlocal total
        if isinstance(value, str):
            new, n = scrub(value)
            total += n
            return new
        if isinstance(value, list):
            return [fix(v) for v in value]
        if isinstance(value, dict):
            return {k: (fix(v) if k in ("text", "content", "system") else v) for k, v in value.items()}
        return value

    out = dict(body)
    if "system" in out:
        out["system"] = fix(out["system"])
    out["messages"] = [m | {"content": fix(m.get("content"))} for m in body.get("messages", [])]
    return out, total
