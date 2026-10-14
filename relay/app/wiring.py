"""Choose real or offline implementations from settings, in one place."""

from .config import settings


def build_llm():
    if settings.llm_backend == "echo":
        from .llm import EchoLLM

        return EchoLLM()
    from .llm import AnthropicLLM

    return AnthropicLLM(settings.model, settings.max_tokens, settings.refusal_fallback)


def build_extractor():
    if settings.llm_backend == "echo":
        from .memory import NullExtractor

        return NullExtractor()
    from .memory import AnthropicExtractor

    return AnthropicExtractor(settings.memory_model)


def build_quarantine():
    from .quarantine import AnthropicQuarantine

    return AnthropicQuarantine(settings.memory_model)


def build_embedder():
    from .embeddings import HashEmbedder, LocalEmbedder

    return HashEmbedder() if settings.embeddings == "hash" else LocalEmbedder()


def build_reranker():
    if settings.embeddings == "hash":
        return None
    from .embeddings import LocalReranker

    return LocalReranker()
