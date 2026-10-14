import copy
import itertools

from app.llm import LLMResponse

_ids = itertools.count(1)


def text(t: str) -> LLMResponse:
    return LLMResponse([{"type": "text", "text": t}], "end_turn", {"input_tokens": 100, "output_tokens": 20})


def tool_use(*calls: tuple[str, dict], stop_reason: str = "tool_use") -> LLMResponse:
    blocks = [{"type": "tool_use", "id": f"toolu_{next(_ids)}", "name": n, "input": i} for n, i in calls]
    return LLMResponse(blocks, stop_reason, {"input_tokens": 100, "output_tokens": 30})


class ScriptedLLM:
    """Plays back canned responses and records every request, so tests can check what the model was sent."""

    def __init__(self, *responses: LLMResponse):
        self.responses = list(responses)
        self.requests: list[dict] = []

    async def respond(self, *, system, tools, messages, on_text) -> LLMResponse:
        self.requests.append({"system": system, "tools": tools, "messages": copy.deepcopy(messages)})
        r = self.responses.pop(0)
        for b in r.content:
            if b["type"] == "text":
                await on_text(b["text"])
        return r


class FakeExtractor:
    def __init__(self, facts):
        self.facts = facts
        self.seen: list[str] = []

    async def extract(self, customer_text: str):
        self.seen.append(customer_text)
        return self.facts


class FakeQuarantine:
    """Keyword stand-in for the quarantined model. It sees untrusted text; the agent only sees its output."""

    def __init__(self):
        self.seen: list[str] = []

    async def review_themes(self, reviews):
        from app.quarantine import ReviewThemes

        self.seen += reviews
        text = " ".join(reviews).lower()
        praise = [t for t in ("weight", "setup") if t in text][:3]
        complaints = [t for t in ("durability", "waterproofing") if t in text or "leak" in text][:3]
        return ReviewThemes(praise=praise, complaints=complaints)

    async def triage_email(self, subject, body):
        import re

        from app.quarantine import EmailTriage

        text = f"{subject} {body}".lower()
        self.seen.append(text)
        intent = (
            "spam"
            if "lottery" in text
            else "refund"
            if "refund" in text
            else "return"
            if "return" in text
            else "order_status"
            if "where" in text
            else "other"
        )
        return EmailTriage(
            intent=intent,
            order_ids=[int(x) for x in re.findall(r"\b\d{4}\b", text)][:5],
            urgency="high" if "urgent" in text else "normal",
            safety_issue=any(w in text for w in ("gas", "fire", "burn", "injur")),
        )
