FROM nvidia/cuda:12.2.0-base-ubuntu22.04

# Avoid interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Incorporar uv para instalaciones más rápidas (version fija)
COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /bin/uv

# Install Python and system dependencies
# libportaudio2 is required for sounddevice import
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    libportaudio2 \
    git \
    wget \
    unzip \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && rm -rf /var/lib/apt/lists/*

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

# Create models directory
RUN mkdir -p models

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
