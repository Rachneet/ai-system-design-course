"""MCP client for the carrier's tracking server. Third-party output is treated as data, size-limited, and timed."""

import asyncio
import json

from mcp import Client

from .telemetry import tracer


class ShippingClient:
    def __init__(self, target, timeout_s: float = 4.0):
        self.target = target  # a Streamable HTTP URL in production; an MCPServer instance in tests
        self.timeout_s = timeout_s

    async def track(self, tracking_number: str) -> dict:
        # A client-side span is recorded even if the third-party server exports nothing to our backend.
        with tracer.start_as_current_span("mcp.client shipping.track_package") as span:
            span.set_attributes(
                {
                    "mcp.method.name": "tools/call",
                    "gen_ai.tool.name": "track_package",
                    "server.address": str(self.target)[:100],
                }
            )
            async with asyncio.timeout(self.timeout_s), Client(self.target) as client:
                result = await client.call_tool("track_package", {"tracking_number": tracking_number})
            if getattr(result, "is_error", False) or not result.content:
                raise RuntimeError("carrier lookup failed")
            text = result.content[0].text[:2000]
            span.set_attribute("relay.mcp.response_chars", len(text))
            return json.loads(text)
