"""The systems of record as one service: uvicorn helpdesk.servers.main:app (same image, different command)."""

from .app import create_servers_app

app = create_servers_app()
