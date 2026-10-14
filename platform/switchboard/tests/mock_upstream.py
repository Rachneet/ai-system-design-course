"""A stand-in for the Anthropic Messages API: JSON and SSE responses with realistic usage, scripted failures,
and a record of the exact bytes received (to prove the gateway forwards requests unchanged)."""

import asyncio
import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
app.state.fail = {}  # model -> status code to return
app.state.received = []  # raw request bodies
app.state.headers = []
app.state.delay_s = 0.0


def usage_for(body: dict) -> dict:
    text = json.dumps(body.get("messages", []))
    return {
        "input_tokens": max(1, len(text) // 4),
        "output_tokens": 12,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }


@app.post("/v1/messages")
async def messages(request: Request):
    raw = await request.body()
    app.state.received.append(raw)
    app.state.headers.append(dict(request.headers))
    body = json.loads(raw)
    model = body["model"]
    if app.state.delay_s:
        await asyncio.sleep(app.state.delay_s)
    if model in app.state.fail:
        code = app.state.fail[model]
        return JSONResponse(
            {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}, status_code=code
        )
    usage = usage_for(body)
    if not body.get("stream"):
        return JSONResponse(
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [{"type": "text", "text": f"echo from {model}"}],
                "stop_reason": "end_turn",
                "usage": usage,
            }
        )

    async def events():
        start_usage = {k: v for k, v in usage.items() if k != "output_tokens"} | {"output_tokens": 1}
        frames = [
            {
                "type": "message_start",
                "message": {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [],
                    "usage": start_usage,
                },
            },
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": f"streamed from {model}"},
            },
            {"type": "content_block_stop", "index": 0},
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": usage["output_tokens"]},
            },
            {"type": "message_stop"},
        ]
        for f in frames:
            yield f"event: {f['type']}\ndata: {json.dumps(f)}\n\n".encode()

    return StreamingResponse(events(), media_type="text/event-stream")


def chat_usage_for(body: dict) -> dict:
    prompt = max(1, len(json.dumps(body.get("messages", []))) // 4)
    return {"prompt_tokens": prompt + 100, "completion_tokens": 9, "prompt_tokens_details": {"cached_tokens": 100}}


@app.post("/v1/chat/completions")
@app.post("/p2/v1/chat/completions")
async def chat_completions(request: Request):
    """A stand-in for any OpenAI-compatible provider. /p2 is a second provider, for cross-provider fallback."""
    raw = await request.body()
    app.state.received.append(raw)
    app.state.headers.append(dict(request.headers) | {"path": request.url.path})
    body = json.loads(raw)
    model = body["model"]
    if model in app.state.fail:
        return JSONResponse({"error": {"message": "busy", "type": "server_error"}}, status_code=app.state.fail[model])
    usage = chat_usage_for(body)
    if not body.get("stream"):
        return JSONResponse(
            {
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": f"echo from {model}"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": usage,
            }
        )

    async def events():
        yield f"data: {json.dumps({'model': model, 'choices': [{'index': 0, 'delta': {'content': f'streamed from {model}'}}]})}\n\n".encode()
        yield f"data: {json.dumps({'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n".encode()
        if (body.get("stream_options") or {}).get("include_usage"):
            yield f"data: {json.dumps({'model': model, 'choices': [], 'usage': usage})}\n\n".encode()
        yield b"data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
