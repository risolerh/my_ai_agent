# Service Agent Voice

Gateway WebSocket/FastAPI para orquestar servicios externos de voz por gRPC/HTTP/WS.

## Arquitectura
- `service-agent-voice`: frontend web + gateway (`http://localhost:8000`).
- `service-stt`: externo, gRPC (`5002`).
- `service-translate`: externo, gRPC (`5001`).
- `service-tts`: externo, HTTP/WS (`8004`) y opcional gRPC (`5003`).

Este repositorio no levanta STT/Translate/TTS; solo se conecta a ellos.

## Docker Compose (gateway only)
Desde este directorio:

```bash
docker compose up --build
```

Levanta solo:
- `service-agent-voice`: `http://localhost:8000`

## Variables de entorno relevantes
- `STT_SERVICE_HOST` (default en código: `127.0.0.1`; en compose: `host.docker.internal`)
- `STT_SERVICE_PORT` (default `5002`)
- `TRANSLATE_SERVICE_HOST` (default en código: `127.0.0.1`; en compose: `host.docker.internal`)
- `TRANSLATE_SERVICE_PORT` (default `5001`)
- `TTS_HTTP_URL` (default `http://127.0.0.1:8004`)
- `TTS_STREAM_URL` (default `ws://127.0.0.1:8004/ws/tts-stream`)
- `OLLAMA_BASE_URL` (default `http://host.docker.internal:11434` en compose)

## Endpoints del gateway
- `GET /`
- `GET /api/models`
- `GET /api/languages`
- `GET /api/ollama-models`
- `GET /api/tts-voices`
- `WS /ws/stream`

## Desarrollo local con uv
Gateway web:

```bash
uv sync
uv run uvicorn server:app --host 0.0.0.0 --port 8000
```

Desktop (opcional):

```bash
uv sync --extra desktop
uv run python main.py
```

Tooling de protos (opcional):

```bash
uv sync --extra dev
```
