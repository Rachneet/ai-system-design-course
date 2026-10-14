"""Tracing with OpenTelemetry, following the GenAI semantic conventions (status: Development, so pin and expect
renames). Spans export over OTLP when OTEL_EXPORTER_OTLP_ENDPOINT is set; otherwise tracing is a no-op.

Message content is NOT recorded unless RELAY_TRACE_CONTENT=1, and then only after redaction.
"""

import os
import re

from opentelemetry import propagate, trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .guardrails import redact_cards

tracer = trace.get_tracer("relay")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Needs separators between digit groups, so order numbers and plain IDs (e.g. 1234567890) are left alone.
PHONE = re.compile(
    r"(?<![\w+])(?:\+\d{1,3}[ .-]?)?(?:\(\d{2,4}\)[ .-]?|\d{2,4}[ .-])\d{3,4}[ .-]\d{3,4}(?!\w)"
)
TRACE_CONTENT = os.environ.get("RELAY_TRACE_CONTENT") == "1"


def setup(service: str, version: str = os.environ.get("RELAY_VERSION", "dev")) -> None:
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or isinstance(
        trace.get_tracer_provider(), TracerProvider
    ):
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": service,
                "service.version": version,
                "deployment.environment.name": os.environ.get("RELAY_ENV", "dev"),
            }
        )
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)


def redact(text: str) -> str:
    text = redact_cards(text)[0]
    return PHONE.sub("[PHONE]", EMAIL.sub("[EMAIL]", text))


def record_content(span, key: str, text: str) -> None:
    if TRACE_CONTENT and text:
        span.set_attribute(key, redact(text)[:4000])


def inject() -> dict:
    carrier: dict = {}
    propagate.inject(carrier)
    return carrier


def link_from(carrier: dict | None) -> list[trace.Link]:
    """A job runs long after the request that queued it, so it links to that trace instead of extending it."""
    if not carrier:
        return []
    ctx = trace.get_current_span(propagate.extract(carrier)).get_span_context()
    return [trace.Link(ctx)] if ctx.is_valid else []
