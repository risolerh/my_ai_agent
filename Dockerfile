FROM python:3.11-slim

# Incorporar uv para instalaciones más rápidas (version fija)
COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /bin/uv

WORKDIR /app

# Instalar dependencias del proyecto con uv lock
COPY pyproject.toml uv.lock ./
ENV UV_CACHE_DIR=/data/uv_cache
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
RUN --mount=type=cache,target=/data/uv_cache \
    uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
