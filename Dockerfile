FROM python:3.12-slim
# Non-root user for the runtime; created first so every build layer stays root-owned.
RUN groupadd --system app && useradd --system --gid app --home-dir /app --no-create-home --shell /usr/sbin/nologin app
# Pinned so the uv CLI matches the uv_build range declared in pyproject.toml.
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

WORKDIR /app

# Dependencies first so this layer only rebuilds when pyproject.toml/uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY README.md ./
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

# slim ships no curl, so the probe uses stdlib urllib; a connection or HTTP error raises and exits non-zero.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

# Build runs as root; only the served process drops privileges to the app user.
USER app

CMD ["uvicorn", "agentic_rogue_like.api:app", "--host", "0.0.0.0", "--port", "8000"]
