"""A stand-in for the public MCP registry: two pages of servers in the official response shape."""

from fastapi import FastAPI

app = FastAPI()
PAGES = {
    None: (
        [
            {
                "name": "io.github.alpha/search",
                "description": "Web search",
                "version": "2.1.0",
                "remotes": [{"type": "streamable-http", "url": "https://alpha.example/mcp"}],
            },
            {
                "name": "io.github.beta/files",
                "description": "Files over plain HTTP",
                "version": "0.3.0",
                "remotes": [{"type": "streamable-http", "url": "http://beta.example/mcp"}],
            },
        ],
        "page2",
    ),
    "page2": ([{"name": "bad name without slash", "description": "x", "version": "1.0.0"}], None),
}


@app.get("/v0/servers")
async def servers(cursor: str | None = None, limit: int = 30, version: str | None = None):
    items, nxt = PAGES[cursor]
    meta = {"count": len(items)} | ({"nextCursor": nxt} if nxt else {})
    return {"servers": [{"server": s, "_meta": {}} for s in items], "metadata": meta}
