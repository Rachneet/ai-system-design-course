"""Relay's tools. Every limit the prompt mentions is also enforced here: the prompt guides, the code guarantees."""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from .config import settings
from .db import Store

KB_DIR = Path(__file__).parent.parent / "kb"
RETURN_WINDOW_DAYS = 60
USED_RETURN_WINDOW_DAYS = 30  # used tents and sleeping bags
USED_STRICT_CATEGORIES = {"tent", "sleeping_bag"}


class ToolError(Exception):
    """An error the model should see and can act on."""


@dataclass
class Context:
    store: Store
    customer_id: str  # from authentication, never from the model
    session_id: UUID | None = None
    now: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    fn: Callable[..., Awaitable[str]]
    tier: str  # read | write_bounded | write_approval | escalation


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, properties: dict, required: list[str], tier: str = "read"):
    schema = {"type": "object", "properties": properties, "required": required, "additionalProperties": False}

    def register(fn):
        REGISTRY[name] = Tool(name, description, schema, fn, tier)
        return fn

    return register


def specs() -> list[dict]:
    """Tool definitions for the API, sorted so the prompt prefix stays byte-identical (cache-friendly)."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.schema, "strict": True}
        for t in sorted(REGISTRY.values(), key=lambda t: t.name)
    ]


def _order_summary(o: dict) -> str:
    items = ", ".join(f"{i['qty']}x {i['name']}{' (used)' if i.get('used') else ''}" for i in o["items"])
    parts = [f"Order {o['id']}: {o['status']}", f"total ${o['total']:.2f}", f"items: {items}"]
    if o.get("delivered_at"):
        parts.append(f"delivered {o['delivered_at']:%Y-%m-%d}")
    elif o.get("eta"):
        parts.append(f"ETA {o['eta']:%Y-%m-%d}")
    return "; ".join(parts)


def refund_eligibility(order: dict, now: datetime) -> tuple[bool, str]:
    if order["status"] != "delivered" or order["delivered_at"] is None:
        return False, f"Order {order['id']} is {order['status']}; only delivered orders can be refunded."
    days = (now - order["delivered_at"]).days
    used_strict = any(i.get("used") and i.get("category") in USED_STRICT_CATEGORIES for i in order["items"])
    window = USED_RETURN_WINDOW_DAYS if used_strict else RETURN_WINDOW_DAYS
    if days > window:
        return False, (
            f"Order {order['id']} was delivered {days} days ago; the return window is {window} days "
            f"[POL-RETURNS-2026]. Offer the warranty route if the item is defective [POL-WARRANTY-2026]."
        )
    return True, f"Eligible: delivered {days} days ago, window {window} days."


async def _owned_order(ctx: Context, order_id: int) -> dict:
    order = await ctx.store.fetch_order(order_id, ctx.customer_id)
    if order is None:
        raise ToolError(f"No order {order_id} for this customer. Ask them to double-check the number.")
    return order


@tool(
    "get_order",
    "Look up one of the current customer's orders by its number. Returns status, items, total, and delivery "
    "date or ETA, plus whether it is eligible for a refund.",
    {"order_id": {"type": "integer", "description": "Order number, e.g. 1042"}},
    ["order_id"],
)
async def get_order(ctx: Context, order_id: int) -> str:
    order = await _owned_order(ctx, order_id)
    _, eligibility = refund_eligibility(order, ctx.now)
    refund = await ctx.store.refund_for(order_id)
    note = f" Already refunded ${refund['amount']:.2f}." if refund else ""
    return f"{_order_summary(order)}. Refund check: {eligibility}{note}"


@tool(
    "list_orders",
    "List the current customer's 10 most recent orders. Use when they do not know the order number.",
    {},
    [],
)
async def list_orders(ctx: Context) -> str:
    rows = await ctx.store.list_orders(ctx.customer_id)
    if not rows:
        return "This customer has no orders."
    return "\n".join(f"Order {r['id']}: {r['status']}, ${r['total']:.2f}" for r in rows)


@tool(
    "search_kb",
    "Search Northwind's policies and FAQs. Use for questions about returns, warranty, shipping, and products. "
    "Returns matching passages with document IDs to cite in brackets, like [POL-RETURNS-2026].",
    {"query": {"type": "string", "description": "A short search query, e.g. 'return window used tent'"}},
    ["query"],
)
async def search_kb(ctx: Context, query: str) -> str:
    # Lab 1 keyword search over local Markdown. Lab 2 replaces this with hybrid retrieval in Postgres.
    terms = set(re.findall(r"[a-z0-9]+", query.lower())) - {"the", "a", "an", "for", "of", "to", "my", "is"}
    scored = []
    for path in sorted(KB_DIR.glob("*.md")):
        text = path.read_text()
        score = sum(text.lower().count(t) for t in terms)
        if score:
            scored.append((score, path.stem, text.strip()))
    if not scored:
        return "No matching documents. Say you are not sure and offer to connect them with the team."
    scored.sort(reverse=True)
    return "\n\n".join(f'<doc id="{doc_id}">\n{text}\n</doc>' for _, doc_id, text in scored[:2])


@tool(
    "issue_refund",
    f"Refund a delivered order, up to ${settings.refund_limit:.0f} and never more than the order total. "
    "For larger amounts use request_refund_approval. Check eligibility with get_order first.",
    {
        "order_id": {"type": "integer"},
        "amount": {"type": "number", "description": "Refund amount in USD"},
        "reason": {"type": "string", "description": "Short reason, e.g. 'torn rain fly on arrival'"},
    },
    ["order_id", "amount", "reason"],
    tier="write_bounded",
)
async def issue_refund(ctx: Context, order_id: int, amount: float, reason: str) -> str:
    order = await _owned_order(ctx, order_id)
    ok, why = refund_eligibility(order, ctx.now)
    if not ok:
        raise ToolError(why)
    if amount <= 0 or amount > float(order["total"]):
        raise ToolError(f"Amount must be between $0 and the order total ${order['total']:.2f}.")
    if amount > settings.refund_limit:
        raise ToolError(
            f"${amount:.2f} is above the ${settings.refund_limit:.0f} limit. Use request_refund_approval."
        )
    if not await ctx.store.create_refund(order_id, amount, reason):
        existing = await ctx.store.refund_for(order_id)
        return f"Order {order_id} was already refunded ${existing['amount']:.2f}. No new refund was issued."
    return f"Refunded ${amount:.2f} for order {order_id}. The customer sees it in 3 to 5 business days."


@tool(
    "request_refund_approval",
    f"Ask a human to approve a refund above ${settings.refund_limit:.0f}. A teammate reviews within 4 business hours.",
    {"order_id": {"type": "integer"}, "amount": {"type": "number"}, "reason": {"type": "string"}},
    ["order_id", "amount", "reason"],
    tier="write_approval",
)
async def request_refund_approval(ctx: Context, order_id: int, amount: float, reason: str) -> str:
    order = await _owned_order(ctx, order_id)
    ok, why = refund_eligibility(order, ctx.now)
    if not ok:
        raise ToolError(why)
    if amount > float(order["total"]):
        raise ToolError(f"Amount exceeds the order total ${order['total']:.2f}.")
    approval_id = await ctx.store.create_approval(order_id, amount, reason, ctx.session_id)
    return f"Approval request #{approval_id} created for ${amount:.2f}. A teammate reviews it within 4 business hours."


@tool(
    "escalate_to_human",
    "Hand the conversation to a human teammate. Use immediately for safety issues (injury, fire, gas), "
    "legal threats, or when the customer asks for a person.",
    {"reason": {"type": "string"}},
    ["reason"],
    tier="escalation",
)
async def escalate_to_human(ctx: Context, reason: str) -> str:
    ticket = await ctx.store.create_escalation(ctx.customer_id, ctx.session_id, reason)
    return f"Escalated as ticket #{ticket}. Tell the customer a teammate will reply by email within 4 hours."
