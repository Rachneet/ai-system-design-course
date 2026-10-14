"""Long-term memory: extract durable facts after a session, in the background, from the customer's own words."""

import re
from typing import Literal, Protocol
from uuid import UUID

import anthropic
from pydantic import BaseModel

from .db import Store

EXTRACT_PROMPT = """From the customer's messages below, list durable facts worth remembering for future
support conversations: preferences, products they own, recurring issues, constraints. Only include facts likely
to stay true for months, stated by the customer. Do not include payment details, addresses, one-off details,
or anything they asked us to forget. Write each fact as a short third-person statement."""

# Memory stores facts, never instructions. Text that reads like a command is dropped (memory poisoning defence).
IMPERATIVE = re.compile(
    r"\b(ignore|disregard|always|never|must|should|approve|refund|pre-?approved|instruction|system prompt|vip)\b",
    re.IGNORECASE,
)


class Fact(BaseModel):
    fact: str
    category: Literal["preference", "product", "issue", "constraint"]
    confidence: float


class Facts(BaseModel):
    facts: list[Fact]


class Extractor(Protocol):
    async def extract(self, customer_text: str) -> list[Fact]: ...


class AnthropicExtractor:
    def __init__(self, model: str):
        self.client = anthropic.AsyncAnthropic()
        self.model = model

    async def extract(self, customer_text: str) -> list[Fact]:
        resp = await self.client.messages.parse(
            model=self.model,
            max_tokens=1024,
            system=EXTRACT_PROMPT,
            messages=[
                {"role": "user", "content": f"<customer_messages>\n{customer_text}\n</customer_messages>"}
            ],
            output_format=Facts,
        )
        return resp.parsed_output.facts if resp.parsed_output else []


def customer_text(messages: list[dict]) -> str:
    """Only what the customer typed. Tool results (reviews, emails, KB text) are third-party content."""
    lines = []
    for m in messages:
        if m["role"] != "user":
            continue
        content = m["content"]
        if isinstance(content, str):
            lines.append(content)
        else:
            lines += [
                b["text"]
                for b in content
                if b.get("type") == "text" and not b["text"].startswith("<guardrail>")
            ]
    return "\n".join(lines)


def acceptable(fact: Fact, min_confidence: float = 0.7) -> bool:
    return fact.confidence >= min_confidence and len(fact.fact) <= 200 and not IMPERATIVE.search(fact.fact)


async def remember(
    store: Store, extractor: Extractor, customer_id: str, session_id: UUID, messages: list[dict]
) -> int:
    text = customer_text(messages)
    if not text.strip():
        return 0
    facts = [f for f in await extractor.extract(text) if acceptable(f)]
    await store.add_memories(customer_id, session_id, [(f.fact, f.category) for f in facts])
    return len(facts)


class NullExtractor:
    """Used when no model backend is configured (offline smoke tests)."""

    async def extract(self, customer_text: str) -> list[Fact]:
        return []
