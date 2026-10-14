"""A small carrier-tracking MCP server, standing in for a third-party shipping provider.

    uv run python -m mcp_servers.shipping        # Streamable HTTP on :8090/mcp

The MCP SDK extracts W3C trace context from each request's params._meta, so this server's spans join the
caller's trace when both sides export to the same backend.
"""

import asyncio
import hashlib
import os
from datetime import UTC, datetime, timedelta

from mcp.server.mcpserver import MCPServer

server = MCPServer("shipping")
STATUSES = ["label_created", "in_transit", "out_for_delivery", "delivered"]


@server.tool()
async def track_package(tracking_number: str) -> dict:
    """Current status and last scan for a parcel, by carrier tracking number (e.g. NW1042)."""
    delay = float(os.environ.get("SHIPPING_DELAY_S", "0"))
    if delay:
        await asyncio.sleep(delay)
    h = int(hashlib.sha256(tracking_number.encode()).hexdigest(), 16)  # deterministic fake data
    status = STATUSES[h % len(STATUSES)]
    when = datetime(2026, 10, 1, tzinfo=UTC) - timedelta(hours=h % 48)
    return {
        "tracking_number": tracking_number,
        "status": status,
        "last_scan": f"{when:%Y-%m-%d %H:%M} UTC",
        "location": ["Denver, CO", "Salt Lake City, UT", "Chicago, IL", "Customer address"][h % 4],
    }


if __name__ == "__main__":
    server.run("streamable-http", host="0.0.0.0", port=int(os.environ.get("PORT", "8090")))
