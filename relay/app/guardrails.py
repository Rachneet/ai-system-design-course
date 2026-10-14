"""Guardrails outside the model: deterministic checks first. Each one is tested and has a defined failure path."""

import re

from .config import settings

CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
CITATION = re.compile(r"\[([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\]")
AMOUNT = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)")
# A promise, not a mention: "I've refunded", "you'll receive", "is being processed".
PROMISE = re.compile(
    r"\b(refunded|will refund|i'll refund|i have refunded|i've refunded|issued|issuing|processed|processing|you'll (?:get|receive|see)|you will (?:get|receive|see))\b",
    re.IGNORECASE,
)


def luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for d in reversed(digits):
        n = int(d)
        if alt:
            n = n * 2 - 9 if n * 2 > 9 else n * 2
        total += n
        alt = not alt
    return total % 10 == 0


def redact_cards(text: str) -> tuple[str, int]:
    """Replace real-looking card numbers (13-19 digits passing the Luhn check). Order numbers do not pass."""
    count = 0

    def sub(m: re.Match) -> str:
        nonlocal count
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            count += 1
            return "[CARD REDACTED]"
        return m.group()

    return CARD.sub(sub, text), count


def check_reply(reply: str, retrieved: set[str], tool_calls: list[dict]) -> list[str]:
    """Returns violations; empty means the reply may be shown."""
    problems = []
    unknown = sorted(set(CITATION.findall(reply)) - retrieved)
    if unknown:
        problems.append(f"cites {', '.join(unknown)}, which were not in this turn's search results")
    approved = any(c["name"] == "request_refund_approval" and not c["is_error"] for c in tool_calls)
    for sentence in re.split(r"(?<=[.!?])\s+", reply):
        if approved or "approv" in sentence.lower() or not PROMISE.search(sentence):
            continue
        for amount in AMOUNT.findall(sentence):
            if float(amount.replace(",", "")) > settings.refund_limit:
                problems.append(f"mentions a ${amount} refund without an approval request")
    if redact_cards(reply)[1]:
        problems.append("contains a card number")
    return problems
