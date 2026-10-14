"""A goal-driven simulated customer for multi-turn cases (the tau-bench approach)."""

from typing import Protocol

import anthropic

DONE = "###DONE###"

PROMPT = """You are role-playing a customer of Northwind Outfitters, an outdoor gear store, chatting with its
support assistant.
Goal: {goal}
Facts you know (reveal one only when asked or when it is natural): {facts}
Personality: {persona}
Write only the customer's next message, one or two short sentences, as a real customer would. Never write the
assistant's lines. When your goal is met or clearly impossible, end your message with {done}."""


class Simulator(Protocol):
    async def next_message(self, spec: dict, transcript: list[tuple[str, str]]) -> str: ...


class AnthropicSimulator:
    def __init__(self, model: str):
        self.client = anthropic.AsyncAnthropic()
        self.model = model

    async def next_message(self, spec: dict, transcript: list[tuple[str, str]]) -> str:
        # Roles are swapped: the simulator is the "assistant" and Relay's replies arrive as "user" turns.
        messages = [{"role": "user", "content": "(The chat opens. Write your first message.)"}]
        for customer, relay in transcript:
            messages += [
                {"role": "assistant", "content": customer},
                {"role": "user", "content": relay or "(no reply)"},
            ]
        resp = await self.client.messages.create(
            model=self.model,
            max_tokens=300,
            messages=messages,
            system=PROMPT.format(
                goal=spec["goal"],
                facts=spec.get("facts", "none"),
                persona=spec.get("persona", "polite"),
                done=DONE,
            ),
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()
