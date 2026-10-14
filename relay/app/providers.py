"""Model specs and provider presets: one string picks the provider and the model.

    anthropic:claude-opus-5-5          native Anthropic Messages API (prompt caching, refusal fallback)
    openai:gpt-5                       OpenAI
    gemini:gemini-2.5-flash            Google Gemini through its OpenAI-compatible endpoint
    openrouter:qwen/qwen3-235b-a22b    OpenRouter: hundreds of models behind one key
    huggingface:meta-llama/Llama-3.3-70B-Instruct   Hugging Face Inference Providers
    ollama:qwen3:8b                    a local open-weights model through Ollama
    vllm:Qwen/Qwen3-32B                your own vLLM server
    compatible:any-model               any other OpenAI-compatible endpoint (LiteLLM proxy, Groq, Together, a gateway)

Model IDs change often: check each provider's model list. A spec without a known provider prefix uses
RELAY_DEFAULT_PROVIDER, except that "claude-*" always means Anthropic. Only the prefix before the first colon is the provider, so model names may contain colons (qwen3:8b).
"""

import os
from dataclasses import dataclass

from .config import settings


@dataclass(frozen=True)
class Preset:
    base_url: str | None  # None means the native Anthropic API
    key_env: str | None  # environment variable holding the API key; None for keyless local servers
    max_tokens_param: str = "max_tokens"  # OpenAI's newer models only accept max_completion_tokens


PRESETS = {
    "anthropic": Preset(None, "ANTHROPIC_API_KEY"),
    "openai": Preset("https://api.openai.com/v1", "OPENAI_API_KEY", "max_completion_tokens"),
    "gemini": Preset("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"),
    "openrouter": Preset("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "huggingface": Preset("https://router.huggingface.co/v1", "HF_TOKEN"),
    "ollama": Preset(os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"), None),
    "vllm": Preset(os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1"), "VLLM_API_KEY"),
    "compatible": Preset(settings.compatible_base_url or None, "RELAY_COMPATIBLE_API_KEY"),
}
ALIASES = {"hf": "huggingface", "google": "gemini", "claude": "anthropic", "openai-compatible": "compatible"}


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


def parse_spec(spec: str, default_provider: str | None = None) -> ModelSpec:
    head, sep, rest = spec.partition(":")
    name = ALIASES.get(head.lower(), head.lower())
    if sep and name in PRESETS:
        return ModelSpec(name, rest)
    if spec.startswith("claude-"):
        return ModelSpec("anthropic", spec)
    return ModelSpec(default_provider or settings.default_provider, spec)


def build_model(
    spec: str, *, max_tokens: int | None = None, max_retries: int = 2, refusal_fallback: bool = False
):
    """An LLM for a spec. Every result implements respond (agent loop), parse (structured output) and complete."""
    s = parse_spec(spec)
    preset = PRESETS[s.provider]
    max_tokens = max_tokens or settings.max_tokens
    if preset.base_url is None and s.provider == "anthropic":
        from .llm import AnthropicLLM

        return AnthropicLLM(s.model, max_tokens, refusal_fallback, max_retries=max_retries)
    if preset.base_url is None:
        raise ValueError(f"{s.provider}: set RELAY_COMPATIBLE_BASE_URL to the endpoint's /v1 URL")
    from .llm import OpenAICompatLLM

    key = os.environ.get(preset.key_env, "") if preset.key_env else ""
    return OpenAICompatLLM(
        s.model,
        max_tokens,
        base_url=preset.base_url,
        api_key=key or "unused",  # local servers ignore it, but the SDK requires a value
        provider=s.provider,
        max_tokens_param=preset.max_tokens_param,
        max_retries=max_retries,
    )
