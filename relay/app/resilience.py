"""Retries, a circuit breaker, a fallback model, and fault injection for game days."""

import asyncio
import random
import time

import anthropic
import openai

from . import metrics
from .llm import LLM, LLMResponse


class InjectedFault(Exception):
    """Raised on purpose by FaultInjectingLLM (RELAY_FAULT_RATE) to rehearse an outage."""


RETRYABLE = (  # the same failures from every SDK: rate limits, provider 5xx, network
    anthropic.RateLimitError,
    anthropic.InternalServerError,
    anthropic.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
    openai.APIConnectionError,
    InjectedFault,
)


class CircuitBreaker:
    """Opens after `threshold` consecutive failures; lets one trial call through after `reset_after_s`."""

    def __init__(self, threshold: int = 5, reset_after_s: float = 30.0, clock=time.monotonic):
        self.threshold, self.reset_after_s, self.clock = threshold, reset_after_s, clock
        self.failures, self.opened_at = 0, None

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        return "half_open" if self.clock() - self.opened_at >= self.reset_after_s else "open"

    def allow(self) -> bool:
        return self.state != "open"

    def success(self) -> None:
        self.failures, self.opened_at = 0, None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold or self.state == "half_open":
            self.opened_at = self.clock()


def retry_after(e: Exception) -> float | None:
    headers = getattr(getattr(e, "response", None), "headers", None) or {}
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


class ResilientLLM:
    """Wraps the primary model. SDK retries must be off (max_retries=0) so attempts do not multiply."""

    def __init__(
        self,
        primary: LLM,
        fallback: LLM | None = None,
        attempts: int = 3,
        base_s: float = 0.5,
        cap_s: float = 8.0,
        deadline_s: float = 20.0,
        breaker: CircuitBreaker | None = None,
        sleep=asyncio.sleep,
    ):
        self.primary, self.fallback = primary, fallback
        self.attempts, self.base_s, self.cap_s, self.deadline_s = attempts, base_s, cap_s, deadline_s
        self.breaker = breaker or CircuitBreaker()
        self.sleep = sleep
        self.force_fallback = False  # kill switch: flags agent.force_fallback

    @property
    def model(self) -> str:
        return getattr(self.primary, "model", "unknown")

    async def _fallback(self, reason: str, **kwargs) -> LLMResponse:
        if self.fallback is None:
            raise RuntimeError(f"primary model unavailable ({reason}) and no fallback configured")
        metrics.fallbacks.labels(reason=reason).inc()
        resp = await self.fallback.respond(**kwargs)
        resp.usage["model"] = getattr(self.fallback, "model", "fallback")
        return resp

    async def respond(self, *, system, tools, messages, on_text) -> LLMResponse:
        kwargs = {"system": system, "tools": tools, "messages": messages, "on_text": on_text}
        if self.force_fallback:
            return await self._fallback("forced", **kwargs)
        if not self.breaker.allow():
            return await self._fallback("circuit_open", **kwargs)
        emitted = False

        async def tracked(t: str) -> None:
            nonlocal emitted
            emitted = True
            await on_text(t)

        start = time.monotonic()
        for attempt in range(self.attempts):
            try:
                resp = await self.primary.respond(
                    system=system, tools=tools, messages=messages, on_text=tracked
                )
                self.breaker.success()
                return resp
            except RETRYABLE as e:
                metrics.provider_errors.labels(model=self.model, type=type(e).__name__).inc()
                self.breaker.failure()
                if emitted:  # text already reached the user: a retry would duplicate it
                    raise
                delay = retry_after(e) or random.uniform(
                    0, min(self.cap_s, self.base_s * 2**attempt)
                )  # full jitter
                last = attempt == self.attempts - 1 or time.monotonic() - start + delay > self.deadline_s
                if last or not self.breaker.allow():
                    return await self._fallback("primary_failed", **kwargs)
                await self.sleep(delay)
        return await self._fallback("primary_failed", **kwargs)


class FaultInjectingLLM:
    """Fails a fraction of calls on purpose. Only for game days and tests: RELAY_FAULT_RATE=0.5."""

    def __init__(self, inner: LLM, rate: float, rng: random.Random | None = None):
        self.inner, self.rate, self.rng = inner, rate, rng or random.Random()
        self.model = getattr(inner, "model", "unknown")

    async def respond(self, **kwargs) -> LLMResponse:
        if self.rng.random() < self.rate:
            raise InjectedFault("injected provider failure (game day)")
        return await self.inner.respond(**kwargs)
