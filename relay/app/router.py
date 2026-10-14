"""Route simple intents to a small model with read-only tools. Off by default: turn it on only after the eval
suite shows every category holds its pass rate on the routed system (flag routing.enabled)."""

from typing import Literal, Protocol

from pydantic import BaseModel

from .llm import StructuredLLM

Intent = Literal[
    "order_status", "policy_question", "product_question", "refund", "return", "complaint", "safety", "other"
]
SIMPLE = {"order_status", "policy_question", "product_question"}
SIMPLE_TIERS = frozenset({"read", "escalation"})  # misrouted refund requests can still escalate, never act


class Classified(BaseModel):
    intent: Intent


class Router(Protocol):
    async def classify(self, message: str) -> Intent: ...


class ModelRouter:
    def __init__(self, llm: StructuredLLM):
        self.llm = llm

    async def classify(self, message: str) -> Intent:
        out = await self.llm.parse(
            system="Classify the customer's latest message for an outdoor gear store's support assistant.",
            user=message[:2000],
            schema=Classified,
            max_tokens=64,
        )
        return out.intent if out else "other"


def is_simple(intent: Intent) -> bool:
    return intent in SIMPLE
