"""Choose real or offline implementations from settings, in one place."""

from .config import settings


def build_llm():
    if settings.llm_backend == "echo":
        from .llm import EchoLLM

        return EchoLLM()
    from .providers import build_model
    from .resilience import FaultInjectingLLM, ResilientLLM

    # The fallback may be another provider entirely: an outage at one vendor is the case it exists for.
    primary = build_model(settings.model, max_retries=0, refusal_fallback=settings.refusal_fallback)
    if settings.fault_rate > 0:
        primary = FaultInjectingLLM(primary, settings.fault_rate)
    fallback = build_model(settings.fallback_model, max_retries=1, refusal_fallback=settings.refusal_fallback)
    return ResilientLLM(primary, fallback)


def build_small_llm():
    if settings.llm_backend == "echo":
        from .llm import EchoLLM

        return EchoLLM()
    from .providers import build_model

    return build_model(settings.router_model, refusal_fallback=settings.refusal_fallback)


def build_router():
    if settings.llm_backend == "echo":
        return None
    from .providers import build_model
    from .router import ModelRouter

    return ModelRouter(build_model(settings.router_model))


def build_judge():
    if settings.llm_backend == "echo":
        return None
    from .judges import ModelJudge
    from .providers import build_model

    return ModelJudge(build_model(settings.judge_model))


def build_shipping():
    if not settings.shipping_mcp_url:
        return None
    from .shipping import ShippingClient

    return ShippingClient(settings.shipping_mcp_url)


def build_extractor():
    if settings.llm_backend == "echo":
        from .memory import NullExtractor

        return NullExtractor()
    from .memory import ModelExtractor
    from .providers import build_model

    return ModelExtractor(build_model(settings.memory_model))


def build_quarantine():
    from .providers import build_model
    from .quarantine import ModelQuarantine

    return ModelQuarantine(build_model(settings.memory_model))


def build_embedder():
    from .embeddings import HashEmbedder, LocalEmbedder

    return HashEmbedder() if settings.embeddings == "hash" else LocalEmbedder()


def build_reranker():
    if settings.embeddings == "hash":
        return None
    from .embeddings import LocalReranker

    return LocalReranker()
