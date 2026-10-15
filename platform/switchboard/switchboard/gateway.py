"""The data plane: POST /v1/messages (Anthropic Messages API) and POST /v1/chat/completions (OpenAI-compatible,
for every other provider). Both run the same keys, limits, budgets, PII policy, fallbacks and metering."""

import asyncio
import json
import re
import time
import uuid

import httpx
import structlog
from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from opentelemetry import trace

from . import metrics, pricing
from .budgets import Budgets
from .config import Settings
from .keys import Caller, KeyStore
from .ledger import LedgerWriter
from .limits import Limiter
from .pii import scrub_request
from .upstream import RETRYABLE_STATUS, Breaker, ChatUpstream, ChatUsageParser, Upstream, UsageParser, chat_usage

log = structlog.get_logger("switchboard")
tracer = trace.get_tracer("switchboard")
PASS_HEADERS = ("content-type", "retry-after", "anthropic-ratelimit-requests-remaining", "request-id")
TAG = re.compile(r"[A-Za-z0-9._:/-]{1,128}")  # a unit of work to charge, e.g. ticket:T-1042
CHAT_PASS_HEADERS = ("content-type", "retry-after", "x-ratelimit-remaining-requests", "x-request-id")


def error(status: int, kind: str, message: str, **headers: str) -> JSONResponse:
    """Errors in the Messages API shape, so existing SDKs surface them normally."""
    return JSONResponse(
        {"type": "error", "error": {"type": kind, "message": message}}, status_code=status, headers=headers
    )


def chat_error(status: int, kind: str, message: str, **headers: str) -> JSONResponse:
    """Errors in the OpenAI shape, so OpenAI-compatible SDKs surface them normally."""
    return JSONResponse(
        {"error": {"message": message, "type": kind, "code": None}}, status_code=status, headers=headers
    )


class Gateway:
    def __init__(self, cfg: Settings, pool, upstream: Upstream, chat_upstreams: dict[str, ChatUpstream] | None = None):
        self.cfg, self.pool, self.upstream = cfg, pool, upstream
        self.chat_upstreams = chat_upstreams or {}
        pricing.register(cfg.chat_models)
        self.keys = KeyStore(pool, cfg.key_cache_ttl_s)
        self.limiter = Limiter(pool, cfg.heartbeat_s)
        self.budgets = Budgets(pool, cfg.budget_cache_s)
        self.ledger = LedgerWriter(pool, cfg.ledger_flush_s)
        self.breakers: dict[str, Breaker] = {}
        self.background: set[asyncio.Task] = set()

    def breaker(self, model: str) -> Breaker:
        return self.breakers.setdefault(model, Breaker(self.cfg.breaker_threshold, self.cfg.breaker_reset_s))

    def later(self, coro) -> None:
        """Run bookkeeping outside the request's cancellation scope (a client disconnect must not lose usage)."""
        task = asyncio.create_task(coro)
        self.background.add(task)
        task.add_done_callback(self.background.discard)

    async def drain(self) -> None:
        if self.background:
            await asyncio.gather(*self.background, return_exceptions=True)
        await self.ledger.flush()

    async def start(self) -> None:
        await self.limiter.start()
        await self.ledger.start()

    async def stop(self) -> None:
        if self.background:
            await asyncio.gather(*self.background, return_exceptions=True)
        await self.ledger.stop()  # final flush: graceful shutdown loses nothing
        await self.limiter.stop()

    async def handle(self, request: Request, chat: bool = False) -> Response:
        started = time.perf_counter()
        request_id = "sbr_" + uuid.uuid4().hex
        with tracer.start_as_current_span("switchboard.chat" if chat else "switchboard.messages") as span:
            span.set_attribute("switchboard.request_id", request_id)
            response = await self._handle(request, request_id, started, span, chat)
            response.headers["x-request-id"] = request_id
            return response

    def _serves(self, model: str, chat: bool) -> bool:
        """Each model belongs to one API style: chat_models to /v1/chat/completions, the rest to /v1/messages."""
        in_chat = model in self.cfg.chat_models
        return (
            pricing.known(model)
            and in_chat == chat
            and (not chat or self.cfg.chat_models[model].get("provider") in self.chat_upstreams)
        )

    async def _send(self, candidate: str, payload: bytes, chat: bool, version: str, betas: list[str]):
        if not chat:
            return await self.upstream.send(payload, version, betas)
        spec = self.cfg.chat_models[candidate]
        if spec.get("upstream_model"):
            payload = json.dumps(json.loads(payload) | {"model": spec["upstream_model"]}).encode()
        return await self.chat_upstreams[spec["provider"]].send(payload)

    async def _handle(self, request: Request, request_id: str, started: float, span, chat: bool = False) -> Response:
        fail = chat_error if chat else error  # errors in the shape the caller's SDK expects
        presented = request.headers.get("x-api-key") or request.headers.get("authorization", "").removeprefix("Bearer ")
        caller = await self.keys.verify(presented)
        if caller is None:
            metrics.rejections.labels(reason="auth").inc()
            return fail(401, "authentication_error", "Invalid, expired, or revoked Switchboard key.")
        span.set_attributes({"switchboard.app": caller.app_id, "switchboard.team": caller.team_id})

        raw = await request.body()
        if len(raw) > self.cfg.max_body_bytes:
            metrics.rejections.labels(reason="too_large").inc()
            return fail(413, "request_too_large", f"Request body exceeds {self.cfg.max_body_bytes} bytes.")
        try:
            body = json.loads(raw)
            model = body["model"]
            assert isinstance(model, str) and isinstance(body.get("messages"), list)
        except (ValueError, KeyError, AssertionError, TypeError):
            metrics.rejections.labels(reason="invalid").inc()
            return fail(400, "invalid_request_error", "Body must be a request with a model and a messages list.")

        tag = request.headers.get("x-switchboard-tag")
        if tag is not None and not TAG.fullmatch(tag):
            metrics.rejections.labels(reason="invalid").inc()
            return fail(400, "invalid_request_error", "x-switchboard-tag must be 1 to 128 of A-Z a-z 0-9 . _ : / -")

        if not self._serves(model, chat):
            metrics.rejections.labels(reason="unknown_model").inc()
            return fail(400, "invalid_request_error", f"Model {model} is not available through this gateway.")
        if caller.allowed_models and model not in caller.allowed_models:
            metrics.rejections.labels(reason="model_policy").inc()
            return fail(403, "permission_error", f"This app may not use {model}.")

        wait = self.limiter.take(f"rpm:{caller.app_id}", caller.rpm)
        if wait:
            metrics.rejections.labels(reason="rpm").inc()
            return fail(
                429,
                "rate_limit_error",
                "Request rate limit reached for this app.",
                **{"retry-after": str(int(wait) + 1)},
            )
        estimate = len(raw) // 4 + int(body.get("max_tokens") or 1024)
        wait = self.limiter.take(f"tpm:{caller.app_id}", caller.tpm, estimate)
        if wait:
            metrics.rejections.labels(reason="tpm").inc()
            return fail(
                429, "rate_limit_error", "Token rate limit reached for this app.", **{"retry-after": str(int(wait) + 1)}
            )
        scope = await self.budgets.exhausted(caller.org_id, caller.team_id, caller.app_id)
        if scope:
            metrics.rejections.labels(reason=f"budget_{scope}").inc()
            return fail(
                429,
                "rate_limit_error",
                f"The monthly budget for this {scope} is used up.",
                # Still a 429 for compatibility, but tell the official SDKs not to retry: money will not refill in seconds.
                **{"x-switchboard-limit": f"budget:{scope}", "x-should-retry": "false"},
            )

        forward, findings, audit_body = raw, 0, None
        if caller.pii_mode != "off":
            scrubbed, findings = scrub_request(body)
            metrics.pii.labels(mode=caller.pii_mode).inc(findings)
            if caller.pii_mode == "redact" and findings:
                forward = json.dumps(
                    scrubbed
                ).encode()  # only re-serialise when something changed: caching stays intact
            audit_body = scrubbed  # audit storage never holds unredacted text
        if caller.log_bodies and audit_body is None:
            audit_body = scrub_request(body)[0]

        if chat and body.get("stream") and not (body.get("stream_options") or {}).get("include_usage"):
            # Only the final chunk carries usage, and only when asked for: needed for metering and budgets.
            forward = json.dumps(json.loads(forward) | {"stream_options": {"include_usage": True}}).encode()
        version = request.headers.get("anthropic-version", self.cfg.default_anthropic_version)
        requested_betas = [b.strip() for b in request.headers.get("anthropic-beta", "").split(",") if b.strip()]
        betas = [b for b in requested_betas if b in self.cfg.allowed_beta_headers]
        candidates = [model] + [
            m
            for m in self.cfg.fallbacks.get(model, [])
            if self._serves(m, chat) and (not caller.allowed_models or m in caller.allowed_models)
        ]
        pre_upstream = time.perf_counter() - started
        metrics.overhead.observe(pre_upstream)
        upstream_started = time.perf_counter()

        resp, served, last_error = None, None, "no candidate available"
        for i, candidate in enumerate(candidates):
            breaker, last = self.breaker(candidate), i == len(candidates) - 1
            if not breaker.allow() and not last:
                continue
            payload = forward if candidate == model else json.dumps(json.loads(forward) | {"model": candidate}).encode()
            try:
                attempt = await self._send(candidate, payload, chat, version, betas)
            except httpx.TransportError as e:
                breaker.failure()
                metrics.upstream_errors.labels(model=candidate, kind=type(e).__name__).inc()
                last_error = f"{type(e).__name__} from provider"
                continue
            if attempt.status_code in RETRYABLE_STATUS:
                breaker.failure()
                metrics.upstream_errors.labels(model=candidate, kind=str(attempt.status_code)).inc()
                if not last:
                    await attempt.aclose()  # nothing has reached the client yet, so a fallback is invisible
                    continue
            else:
                breaker.success()
            resp, served = attempt, candidate
            break

        event = {
            "request_id": request_id,
            "requested_model": model,
            "stream": bool(body.get("stream")),
            "pii_findings": findings,
            "tag": tag,
        }
        if resp is None:
            event |= {
                "status": 502,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "ttfb_ms": None,
                "error_type": "upstream_unavailable",
                "served_model": None,
                "usage": {},
            }
            self.later(self.finish(caller, event, estimate, audit_body, None))
            metrics.requests.labels(model=model, status_class="5xx").inc()
            return fail(502, "api_error", f"No upstream model could serve the request ({last_error}).")
        if served != model:
            metrics.fallbacks.labels(requested=model, served=served).inc()
        span.set_attributes(
            {
                "gen_ai.request.model": model,
                "gen_ai.response.model": served,
                "http.response.status_code": resp.status_code,
            }
        )
        headers = {h: resp.headers[h] for h in (CHAT_PASS_HEADERS if chat else PASS_HEADERS) if h in resp.headers}
        headers["x-switchboard-model"] = served
        if set(requested_betas) - set(betas):
            headers["x-switchboard-dropped-betas"] = ",".join(sorted(set(requested_betas) - set(betas)))

        if event["stream"] and resp.status_code == 200:
            headers["server-timing"] = f"gateway;dur={pre_upstream * 1000:.2f}"
            return StreamingResponse(
                self._stream(resp, caller, event, served, started, estimate, audit_body, chat),
                status_code=200,
                headers=headers,
                media_type="text/event-stream",
            )

        data = await resp.aread()
        await resp.aclose()
        upstream_s = time.perf_counter() - upstream_started
        gateway_ms = (time.perf_counter() - started - upstream_s) * 1000
        # Standard Server-Timing header: lets clients and load tests separate gateway time from provider time.
        headers["server-timing"] = f"gateway;dur={gateway_ms:.2f}, upstream;dur={upstream_s * 1000:.2f}"
        usage, error_type = {}, None
        try:
            parsed = json.loads(data)
            if chat:
                usage = chat_usage(parsed.get("usage"))
                error_type = (parsed.get("error") or {}).get("type") if parsed.get("error") else None
            else:
                usage = {k: v for k, v in (parsed.get("usage") or {}).items() if isinstance(v, int)}
                error_type = (parsed.get("error") or {}).get("type") if parsed.get("type") == "error" else None
        except ValueError:
            error_type = "unparseable_response"
        elapsed = int((time.perf_counter() - started) * 1000)
        event |= {
            "status": resp.status_code,
            "served_model": served,
            "usage": usage,
            "latency_ms": elapsed,
            "ttfb_ms": elapsed,
            "error_type": error_type,
        }
        self.later(
            self.finish(
                caller, event, estimate, audit_body, data.decode(errors="replace") if caller.log_bodies else None
            )
        )
        return Response(
            content=data,
            status_code=resp.status_code,
            headers=headers,
            media_type=resp.headers.get("content-type", "application/json"),
        )

    async def _stream(
        self,
        resp: httpx.Response,
        caller: Caller,
        event: dict,
        served: str,
        started: float,
        estimate: int,
        audit_body,
        chat: bool = False,
    ):
        parser, first, status = (ChatUsageParser() if chat else UsageParser()), None, 200
        captured: list[bytes] = []
        try:
            async for chunk in resp.aiter_raw():
                if first is None:
                    first = time.perf_counter()
                parser.feed(chunk)
                if caller.log_bodies and sum(map(len, captured)) < 200_000:
                    captured.append(chunk)
                yield chunk
        except (asyncio.CancelledError, GeneratorExit):
            status = 499  # client went away; the provider call is closed below and partial usage still billed
            raise
        finally:
            await resp.aclose()
            event |= {
                "status": status,
                # Bill under the catalog name we chose: providers may report an alias or a dated snapshot
                # name in the stream, which would miss the price table and record $0.
                "served_model": served,
                "usage": parser.usage,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "ttfb_ms": int((first - started) * 1000) if first else None,
                "error_type": parser.error_type,
            }
            response_text = b"".join(captured).decode(errors="replace") if caller.log_bodies else None
            self.later(self.finish(caller, event, estimate, audit_body, response_text))

    async def finish(self, caller: Caller, event: dict, estimate: int, audit_body, response_text) -> None:
        model = event.get("served_model") or event["requested_model"]
        usage = event.get("usage", {})
        spent = pricing.cost_usd(model, usage)
        self.ledger.add(
            caller, event, spent, (audit_body, response_text) if caller.log_bodies and audit_body is not None else None
        )
        actual = sum(
            usage.get(k, 0)
            for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
        )
        self.limiter.refund(f"tpm:{caller.app_id}", caller.tpm, estimate - actual)
        status_class = f"{event['status'] // 100}xx"
        metrics.requests.labels(model=model, status_class=status_class).inc()
        metrics.duration.labels(model=model).observe(event["latency_ms"] / 1000)
        if event.get("ttfb_ms") is not None:
            metrics.ttfb.labels(model=model).observe(event["ttfb_ms"] / 1000)
        for kind, key in (
            ("input", "input_tokens"),
            ("output", "output_tokens"),
            ("cache_read", "cache_read_input_tokens"),
            ("cache_write", "cache_creation_input_tokens"),
        ):
            metrics.tokens.labels(model=model, kind=kind).inc(usage.get(key, 0))
        metrics.cost.labels(model=model, team=caller.team_id).inc(float(spent))
        log.info(
            "request",
            request_id=event["request_id"],
            app=caller.app_id,
            team=caller.team_id,
            model=model,
            status=event["status"],
            latency_ms=event["latency_ms"],
            cost_usd=float(spent),
            fallback=model != event["requested_model"],
            pii_findings=event.get("pii_findings", 0),
        )
