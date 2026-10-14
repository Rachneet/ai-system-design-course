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
