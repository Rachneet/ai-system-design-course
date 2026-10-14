---
id: w5-tracing
week: 5
kind: lesson
title: Tracing requests across agent actions and MCP
short: Tracing agents + MCP
minutes: 45
summary: Instrument an agent so every conversation becomes a navigable trace of model calls, tool calls, retrieval, and remote MCP servers, using OpenTelemetry and its GenAI conventions, with context propagated across process boundaries.
---

## Why logs are not enough

An agent turn might involve a router call, three model calls, five tool calls (two in parallel), a retrieval with reranking, and a call to a remote MCP server that itself queries a database. When a user says "it gave me the wrong refund amount", you need to see that entire tree, in order, with inputs, outputs, timings, and token counts. Flat log lines with no relationship to one another make this nearly impossible.

**Distributed tracing** records each unit of work as a **span** with a start time, duration, attributes, and a parent. All spans for one request share a **trace ID**. The result is a tree you can open and read.

```mermaid
flowchart TB
  T["trace: POST /chat (session 8fa2, user c_77) 7.9 s"]
  T --> R["router.classify · haiku · 210 ms · 640 tok"]
  T --> A["agent.run · 7.4 s · 3 steps"]
  A --> M1["chat claude-sonnet-5-5 · step 1 · 1.9 s · in 9,120 / out 85"]
  A --> P["tools (parallel)"]
  P --> T1["execute_tool get_order · 40 ms"]
  P --> T2["execute_tool search_kb · 610 ms"]
  T2 --> S1["retrieval.hybrid · 70 ms"]
  T2 --> S2["rerank · 230 ms"]
  A --> M2["chat claude-sonnet-5-5 · step 2 · 1.2 s"]
  M2 --> X["mcp tools/call shipping.track · 880 ms (remote server)"]
  A --> M3["chat claude-sonnet-5-5 · step 3 · 2.6 s · out 240"]
  T --> G["guardrails.output · 35 ms"]
```

## OpenTelemetry and the GenAI conventions

[OpenTelemetry](https://opentelemetry.io/docs/languages/python/) (OTel) is the vendor-neutral standard for traces, metrics, and logs. Instrument once, send anywhere: Jaeger, Grafana Tempo, Honeycomb, Datadog, or LLM-focused tools like [Langfuse](https://langfuse.com/docs) and [Arize Phoenix](https://github.com/Arize-ai/phoenix) that accept OTel data.

OTel defines [semantic conventions for generative AI](https://github.com/open-telemetry/semantic-conventions-genai/tree/main/docs/gen-ai): standard span names and attribute keys for model calls, agent operations, and tool executions. Using them means your traces work across tools without custom mapping. Key attributes include:

| Attribute | Example |
|---|---|
| `gen_ai.operation.name` | `chat`, `execute_tool`, `invoke_agent`, `embeddings` |
| `gen_ai.provider.name` | `anthropic` |
| `gen_ai.request.model` / `gen_ai.response.model` | `claude-sonnet-5-5` |
| `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` | `9120` / `85` |
| `gen_ai.response.finish_reasons` | `["tool_use"]` |
| `gen_ai.tool.name` / `gen_ai.tool.call.id` | `get_order` / `toolu_01A…` |
| `gen_ai.conversation.id` | session ID |

The conventions are marked **Development** (not yet stable) and moved to their own repository in 2026, so pin the version you follow and expect renames. Cached tokens, for example, are `gen_ai.usage.cache_read.input_tokens` and `gen_ai.usage.cache_write.input_tokens`. Libraries like [OpenLLMetry](https://github.com/traceloop/openllmetry) and the OTel contrib instrumentations can auto-instrument popular SDKs.

## Instrumenting the agent loop

Auto-instrumentation gives you model calls. Add manual spans for the parts that carry your application's meaning: the agent run, each tool, retrieval stages, guardrails.

```python
from opentelemetry import trace
tracer = trace.get_tracer("relay")

async def run_turn(ctx, messages, on_text):
    with tracer.start_as_current_span("invoke_agent relay") as span:
        span.set_attribute("gen_ai.operation.name", "invoke_agent")
        span.set_attribute("gen_ai.conversation.id", str(ctx.session_id))
        span.set_attribute("relay.prompt_sha", PROMPT_SHA)
        span.set_attribute("enduser.id", ctx.customer_hash)       # hashed, not raw
        for step in range(MAX_STEPS):
            with tracer.start_as_current_span(f"chat {MODEL}") as llm:
                llm.set_attribute("gen_ai.operation.name", "chat")
                llm.set_attribute("gen_ai.request.model", MODEL)
                llm.set_attribute("relay.step", step)
                resp = await call_model(ctx, messages, on_text)
                llm.set_attribute("gen_ai.usage.input_tokens", resp.usage.input_tokens)
                llm.set_attribute("gen_ai.usage.output_tokens", resp.usage.output_tokens)
                llm.set_attribute("gen_ai.usage.cache_read.input_tokens", resp.usage.cache_read_input_tokens or 0)
                llm.set_attribute("gen_ai.usage.cache_write.input_tokens", resp.usage.cache_creation_input_tokens or 0)
                llm.set_attribute("gen_ai.response.finish_reasons", [resp.stop_reason])
            ...

async def run_tool(ctx, block):
    with tracer.start_as_current_span(f"execute_tool {block.name}") as span:
        span.set_attribute("gen_ai.operation.name", "execute_tool")
        span.set_attribute("gen_ai.tool.name", block.name)
        span.set_attribute("gen_ai.tool.call.id", block.id)
        try:
            ...
        except ToolError as e:
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            span.set_attribute("relay.tool.error_kind", type(e).__name__)
            raise
```

Because `asyncio.gather` runs tools inside the current context, parallel tool spans correctly share the agent span as parent.

## Propagating context across services and MCP

A trace is only useful if it crosses process boundaries. When the API enqueues a job for a worker, or calls a remote MCP server, the trace context (trace ID and parent span ID) must travel with the request so downstream spans attach to the same trace.

- **HTTP**: OTel's W3C `traceparent` header. Auto-instrumented HTTP clients and servers (httpx, FastAPI) inject and extract it.
- **Queues**: put the `traceparent` in the job payload when enqueuing; extract it in the worker and start the job span as a child (or as a linked span for long-delayed jobs).
- **MCP**: the [Model Context Protocol](https://modelcontextprotocol.io/) sends JSON-RPC messages over stdio or Streamable HTTP. The OpenTelemetry MCP convention puts the W3C `traceparent` (and `tracestate`, `baggage`) inside each request's `params._meta` field, unprefixed, on every transport, and the server uses it as the remote parent for its spans. Because it travels in the message body, it works on stdio too. Support varies by SDK version, so verify it end to end: make an MCP tool call and check that the server's spans appear under your agent's trace.

```python
from opentelemetry.propagate import inject, extract

# producer
carrier = {}
inject(carrier)                                # {"traceparent": "00-<trace>-<span>-01"}
await enqueue("extract_memory", {"session_id": sid, "trace": carrier})

# consumer
ctx = extract(job.payload["trace"])
with tracer.start_as_current_span("job extract_memory", context=ctx):
    ...
```

> [!warn] Third-party MCP servers you do not control will not send spans to your backend. Record a client-side span for every MCP call (server name, tool name, duration, error, response size) so you can at least see their latency and failures from your side.

## What to capture, and what not to

Traces are most useful when you can read the actual prompts and responses. They are also full of personal data. Decide deliberately:

| Capture | Default |
|---|---|
| Model, tokens, latency, finish reason, step, tool names, errors | Always |
| Prompt hash, model config, feature flags, deploy SHA | Always |
| Full message content and tool arguments/results | In a restricted store with retention limits, or sampled, or redacted |
| User identifiers | Hashed or pseudonymous IDs; raw only where policy allows |
| Secrets, card numbers | Never (redact before export) |

The OTel GenAI conventions keep message content out of span attributes by default and make content capture opt-in, for this reason. Apply redaction in an exporter or processor, so it cannot be forgotten in application code.

## Sampling

High-volume systems cannot keep every trace. Typical policy:

- **Head sampling** keeps a percentage chosen at the start of the request (for example 10%).
- **Tail sampling** decides after the trace completes: keep **all** traces with errors, guardrail firings, step-limit hits, high cost, high latency, or negative user feedback, plus a random sample of the rest. Tail sampling needs a collector (the OTel Collector) that buffers spans per trace.

For AI systems, tail sampling is almost always worth it: the interesting traces are rare, and they are the ones you need for error analysis.

## From traces to evals

Traces are the raw material for Week 3's eval datasets. Make the path short:

1. A user gives a thumbs-down, or an online judge fails a conversation.
2. The trace ID is attached to that feedback.
3. A reviewer opens the trace, labels the failure category, and clicks "add to dataset", which runs your trace-to-case converter.

Tools like Langfuse and Phoenix have dataset features for exactly this loop. You can also build it with a small script against your trace store.

## Design review questions

> [!interview] Open the trace for the slowest conversation yesterday. Which span dominated?

> [!interview] When a worker processes a memory job, can you see which chat request caused it?

> [!interview] Where does message content in traces go, who can read it, and when is it deleted?

> [!interview] Which traces are guaranteed to be kept under your sampling policy?

## Further reading

- [OpenTelemetry semantic conventions for GenAI](https://github.com/open-telemetry/semantic-conventions-genai/tree/main/docs/gen-ai).
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/) and [contrib instrumentations](https://github.com/open-telemetry/opentelemetry-python-contrib).
- [OpenLLMetry](https://github.com/traceloop/openllmetry), OTel-based auto-instrumentation for LLM SDKs.
- [Langfuse docs](https://langfuse.com/docs) and [Arize Phoenix](https://github.com/Arize-ai/phoenix), open-source LLM observability.
- [Model Context Protocol](https://modelcontextprotocol.io/).

```quiz
[
  {"q": "What links all spans belonging to one user request?", "options": ["The session ID", "A shared trace ID, with parent-child relationships between spans", "Timestamps", "The model name"], "answer": 1, "why": "Spans share a trace ID and point to their parent, which builds the tree you navigate."},
  {"q": "How do spans in a background worker join the trace of the API request that enqueued the job?", "options": ["Automatically, always", "The producer injects trace context (traceparent) into the job payload and the worker extracts it", "By matching timestamps", "They cannot"], "answer": 1, "why": "Context propagation must cross every boundary, including queues, explicitly."},
  {"q": "Which sampling policy best fits AI systems?", "options": ["Keep 1% randomly", "Tail sampling that keeps all errors, guardrail firings, expensive, slow, or negatively rated traces plus a random sample", "Keep nothing", "Head sampling at 100%"], "answer": 1, "why": "The traces you need for debugging and eval building are rare. Tail sampling keeps them."},
  {"q": "A third-party MCP server you do not control is slow. How do you see it in your traces?", "options": ["You cannot", "Record a client-side span around each MCP call with server, tool, duration, and errors", "Ask the vendor for logs", "Use print statements"], "answer": 1, "why": "Even without their spans, your client span shows their latency and failure rate inside your trace."}
]
```
