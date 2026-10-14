"""Choose real or offline implementations from settings, in one place."""

from .config import settings


def build_llm():
    if settings.llm_backend == "echo":
        from .llm import EchoLLM

        return EchoLLM()
    from .llm import AnthropicLLM
    from .resilience import FaultInjectingLLM, ResilientLLM

    primary = AnthropicLLM(settings.model, settings.max_tokens, settings.refusal_fallback, max_retries=0)
    if settings.fault_rate > 0:
        primary = FaultInjectingLLM(primary, settings.fault_rate)
    fallback = AnthropicLLM(
        settings.fallback_model, settings.max_tokens, settings.refusal_fallback, max_retries=1
    )
    return ResilientLLM(primary, fallback)


def build_small_llm():
    if settings.llm_backend == "echo":
        from .llm import EchoLLM

        return EchoLLM()
    from .llm import AnthropicLLM

    return AnthropicLLM(settings.router_model, settings.max_tokens, settings.refusal_fallback)


def build_router():
    if settings.llm_backend == "echo":
        return None
    from .router import AnthropicRouter

    return AnthropicRouter(settings.router_model)


def build_judge():
    if settings.llm_backend == "echo":
        return None
    from .judges import AnthropicJudge

    return AnthropicJudge(settings.judge_model)


def build_shipping():
    if not settings.shipping_mcp_url:
        return None
    from .shipping import ShippingClient

    return ShippingClient(settings.shipping_mcp_url)


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
