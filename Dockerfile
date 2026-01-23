FROM nvidia/cuda:12.2.0-base-ubuntu22.04

# Avoid interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Incorporar uv para instalaciones más rápidas
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install Python and system dependencies
# libportaudio2 is required for sounddevice import
RUN apt-get update && apt-get install -y \
    python3 \
    libportaudio2 \
    git \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# Usar uv para instalar dependencias (mucho más rápido que pip)
RUN uv pip install --system --no-cache -r requirements.txt

# Copy application code
COPY . .

# Create models directory
RUN mkdir -p models

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
