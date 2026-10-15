"""Model calls through Switchboard's OpenAI-compatible endpoint, tagged job:<id>:<role> so each job's cost can be
charged back. The job's key is all Foundry holds; Switchboard holds the provider keys and the budget."""

import httpx


class ModelError(Exception):
    pass


class Model:
    def __init__(self, base_url: str, key: str, transport=None, timeout_s: float = 120):
        self.http = httpx.Client(base_url=base_url, transport=transport, timeout=timeout_s)
        self.key = key

    def chat(self, model: str, messages: list[dict], tag: str, tools: list[dict] | None = None) -> tuple[dict, int]:
        """Returns the assistant message and the tokens the call used."""
        body = {"model": model, "messages": messages} | ({"tools": tools} if tools else {})
        resp = self.http.post(
            "/v1/chat/completions", json=body, headers={"authorization": f"Bearer {self.key}", "x-switchboard-tag": tag}
        )
        if resp.status_code != 200:
            raise ModelError(f"Switchboard answered {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return data["choices"][0]["message"], int((data.get("usage") or {}).get("total_tokens", 0))
