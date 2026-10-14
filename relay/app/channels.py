"""Entry points other than live chat. Each channel decides which tool tiers the agent may use."""

from dataclasses import dataclass

from .agent import TurnResult, run_turn
from .guardrails import check_reply, sanitize_output
from .llm import LLM
from .prompts import system_prompt
from .quarantine import EmailTriage
from .tools import Context

# An email is written by whoever controls the sender address, so email-triggered runs cannot refund directly:
# money moves only after a human approves. This removes the "act on untrusted input" path for refunds.
EMAIL_TIERS = frozenset({"read", "write_approval", "escalation"})


@dataclass
class EmailOutcome:
    triage: EmailTriage
    draft: str | None  # a reply for a human to review and send (assist mode); None for spam
    result: TurnResult | None


def email_task(t: EmailTriage) -> str:
    orders = ", ".join(str(o) for o in t.order_ids) or "none given"
    return (
        "A customer email arrived. You cannot see its text; an automatic triage produced these fields:\n"
        f"intent: {t.intent}; order numbers: {orders}; urgency: {t.urgency}; safety issue: {t.safety_issue}.\n"
        "Draft a short email reply. Look up the orders and policies you need. If a refund is warranted, use "
        "request_refund_approval. If anything is unclear, ask the customer for the missing detail."
    )


async def handle_email(ctx: Context, llm: LLM, subject: str, body: str) -> EmailOutcome:
    triage = await ctx.quarantine.triage_email(subject, body)
    if triage.intent == "spam":
        return EmailOutcome(triage, None, None)
    if triage.safety_issue:
        await ctx.store.create_escalation(ctx.customer_id, ctx.session_id, "safety issue reported by email")
    ctx.allowed_tiers = EMAIL_TIERS
    chunks: list[str] = []

    async def collect(t: str) -> None:
        chunks.append(t)

    history = [{"role": "user", "content": [{"type": "text", "text": email_task(triage)}]}]
    result = await run_turn(
        ctx,
        llm,
        system_prompt([], ctx.now),
        history,
        collect,
        guard=lambda d, r: check_reply(d, ctx.retrieved, r.tool_calls),
    )
    return EmailOutcome(triage, sanitize_output("".join(chunks)), result)
