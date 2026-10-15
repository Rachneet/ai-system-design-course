"""A scripted model provider, behind Switchboard, in the OpenAI chat-completions shape.

Tests script each agent's turns: script["it-access"] = [calls(...), "final reply"]. The provider tells agents apart
by the first line of the system prompt ("Agent: <id>"), and fills {ticket} and {user} placeholders in tool
arguments from the prompt, as a model would. It never sees provider keys from agents: only Switchboard's.
"""

import json
import re
from itertools import count

from fastapi import FastAPI, Request

app = FastAPI()
state: dict = {"script": {}, "requests": [], "keys": []}
_ids = count(1)


def calls(*items: tuple[str, dict]) -> list:
    """A model turn that calls tools: calls(("idp__unlock_account", {"user_id": "{user}"}))."""
    return [{"name": name, "args": args} for name, args in items]


def reset() -> None:
    state.update(script={}, requests=[], keys=[])


def fill(value, ticket: str, user: str):
    if isinstance(value, str):
        return value.replace("{ticket}", ticket).replace("{user}", user)
    if isinstance(value, dict):
        return {k: fill(v, ticket, user) for k, v in value.items()}
    return value


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    state["requests"].append(body)
    state["keys"].append(request.headers.get("authorization"))
    system = body["messages"][0]["content"]
    agent = re.match(r"Agent: (\S+)", system)[1]
    ticket = re.search(r"Ticket: (\S+)", system)[1]
    user = re.search(r"Signed-in user id: (\S+)", system)[1]
    queue = state["script"].get(agent) or []
    step = queue.pop(0) if queue else f"[{agent} has no scripted turn left]"
    if isinstance(step, str):
        message = {"role": "assistant", "content": step}
    else:
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_{next(_ids)}",
                    "type": "function",
                    "function": {"name": c["name"], "arguments": json.dumps(fill(c["args"], ticket, user))},
                }
                for c in step
            ],
        }
    usage = {"prompt_tokens": 1000, "completion_tokens": 100, "total_tokens": 1100}
    return {
        "id": f"chatcmpl-{next(_ids)}",
        "object": "chat.completion",
        "model": body["model"],
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if step and not isinstance(step, str) else "stop",
            }
        ],
        "usage": usage,
    }
