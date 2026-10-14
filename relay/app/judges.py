"""LLM judges: one binary criterion each, reasoning before verdict, calibrated against labels in judges/*.jsonl."""

from typing import Literal

import anthropic
from pydantic import BaseModel


class Verdict(BaseModel):
    reasoning: str
    verdict: Literal["pass", "fail"]


CRITERIA = {
    "no_unsupported_promise": """Criterion: the assistant must not promise or claim anything (a refund, an approval,
a replacement, a discount, a delivery date, an escalation) unless a tool result in the transcript supports it.
Pass: a tool result shows "Refunded $45.00" and the reply says the $45 refund was issued.
Fail: no refund tool result, but the reply says "your refund is on its way".
Fail: the order tool shows ETA 2026-10-04 and the reply promises delivery tomorrow.
Pass: the reply explains a refund is not possible, or says a teammate will review (and an approval or escalation
tool result exists).""",
    "warranty_route_when_ineligible": """Criterion: when a customer reports a defect on an item that is outside its
return window, the reply must explain that a return or refund is not possible and point them to the warranty
claim route. If the item is still within the return window, or there is no defect, mark pass.
Pass: "It's past the 30-day window for used tents, but a leak like this is covered by our 2-year warranty; you can
claim at northwind.example/warranty."
Fail: "Sorry, it's outside the return window, so there's nothing we can do."
Fail: the reply issues or promises a refund for the out-of-window item.""",
}

TEMPLATE = """You are grading one conversation between a customer and the support assistant of an outdoor gear
store. Grade only the criterion below.

{criterion}

<transcript>
{transcript}
</transcript>

Explain your reasoning in two or three sentences, then give the verdict."""


def render(messages: list[dict]) -> str:
    """A readable transcript including tool calls and results, which judges need to check claims."""
    lines = []
    for m in messages:
        content = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
        for b in content:
            if b["type"] == "text" and b["text"].strip():
                who = "CUSTOMER" if m["role"] == "user" else "ASSISTANT"
                lines.append(f"{who}: {b['text'].strip()}")
            elif b["type"] == "tool_use":
                lines.append(f"TOOL CALL {b['name']}({b['input']})")
            elif b["type"] == "tool_result":
                lines.append(f"TOOL RESULT{' (error)' if b.get('is_error') else ''}: {b['content']}")
    return "\n".join(lines)


class AnthropicJudge:
    def __init__(self, model: str):
        self.client = anthropic.AsyncAnthropic()
        self.model = model  # pin it: a silent judge upgrade changes every score

    async def judge(self, name: str, transcript: str) -> Verdict:
        resp = await self.client.messages.parse(
            model=self.model,
            max_tokens=600,
            output_format=Verdict,
            messages=[
                {"role": "user", "content": TEMPLATE.format(criterion=CRITERIA[name], transcript=transcript)}
            ],
        )
        return resp.parsed_output
