# Service Agent Voice

Proyecto con **dos interfaces** que consumen servicios externos por gRPC/HTTP:
- `main.py`: app de escritorio (Tkinter).
- `server.py`: gateway WebSocket/FastAPI + frontend web.

## Arquitectura actual
- `service-stt` (gRPC `:50052`): Speech-to-Text.
- `service-translate` (gRPC `:50051`): traducción.
- `service-tts` (WebSocket/HTTP `:8000`, gRPC `:50053`): síntesis de voz.
- `service-agent-voice` (`:8000`): orquestador y frontend web.

## Ejecución con Docker Compose
Desde este directorio:

```bash
docker compose up --build
```

Servicios expuestos en host:
- `service-agent-voice`: `http://localhost:8000`
- `service-stt`: gRPC `localhost:5002`, REST `localhost:8003`
- `service-translate`: gRPC `localhost:5001`, REST `localhost:8002`
- `service-tts`: gRPC `localhost:5003`, REST/WS `localhost:8004`

## Variables de entorno relevantes (agent)
- `STT_SERVICE_HOST` (default `127.0.0.1`)
- `STT_SERVICE_PORT` (default `5002`)
- `TRANSLATE_SERVICE_HOST` (default `127.0.0.1`)
- `TRANSLATE_SERVICE_PORT` (default `5001`)
- `TTS_HTTP_URL` (default `http://127.0.0.1:8004`)
- `TTS_STREAM_URL` (default `ws://127.0.0.1:8004/ws/tts-stream`)

## Endpoints del servidor
- `GET /` frontend
- `GET /api/models`
- `GET /api/languages`
- `GET /api/ollama-models`
- `GET /api/tts-voices`
- `WS /ws/stream`

## Modo Desktop
```bash
python main.py
```

`main.py` usa:
- `modules/audio_listener.py` (captura micrófono + STT gRPC)
- `modules/translate.py` (cliente de traducción gRPC)
