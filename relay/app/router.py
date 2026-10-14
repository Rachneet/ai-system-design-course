"""Route simple intents to a small model with read-only tools. Off by default: turn it on only after the eval
suite shows every category holds its pass rate on the routed system (flag routing.enabled)."""

from typing import Literal, Protocol

import anthropic
from pydantic import BaseModel

Intent = Literal[
    "order_status", "policy_question", "product_question", "refund", "return", "complaint", "safety", "other"
]
SIMPLE = {"order_status", "policy_question", "product_question"}
SIMPLE_TIERS = frozenset({"read", "escalation"})  # misrouted refund requests can still escalate, never act


class Classified(BaseModel):
    intent: Intent


class Router(Protocol):
    async def classify(self, message: str) -> Intent: ...


class AnthropicRouter:
    def __init__(self, model: str):
        self.client, self.model = anthropic.AsyncAnthropic(), model

    async def classify(self, message: str) -> Intent:
        resp = await self.client.messages.parse(
            model=self.model,
            max_tokens=64,
            output_format=Classified,
            system="Classify the customer's latest message for an outdoor gear store's support assistant.",
            messages=[{"role": "user", "content": message[:2000]}],
        )
        return resp.parsed_output.intent if resp.parsed_output else "other"


def is_simple(intent: Intent) -> bool:
    return intent in SIMPLE
