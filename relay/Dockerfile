# syntax=docker/dockerfile:1
# One image, two commands: the API (default) and the worker (python -m app.worker).
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 relay
WORKDIR /app
COPY --from=build --chown=relay:relay /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PORT=8080 HF_HOME=/home/relay/.cache/huggingface
USER relay
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz')"
# Shell form so $PORT is expanded; exec so uvicorn receives SIGTERM and drains in-flight streams.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers --timeout-graceful-shutdown 30
