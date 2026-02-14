# Docker Instructions

Este repositorio funciona como **gateway** y depende de microservicios externos (`service_stt`, `service_translate`, `service-tts`).

## Levantar stack completo

```bash
docker compose up --build
```

Incluye:
- `service-agent-voice` (gateway + frontend)
- `service-stt`
- `service-translate`
- `service-tts`

## URLs/puertos esperados
- Agent: `http://localhost:8000`
- STT: gRPC `localhost:5002`, REST `localhost:8003`
- Translate: gRPC `localhost:5001`, REST `localhost:8002`
- TTS: gRPC `localhost:5003`, REST/WS `localhost:8004`

## Verificación rápida
1. Abrir `http://localhost:8000`.
2. Verificar que `GET /api/tts-voices` responda con lista de voces.
3. Iniciar stream en frontend y confirmar eventos `partial`/`final`.

## Configuración por env vars (agent)
- `STT_SERVICE_HOST`, `STT_SERVICE_PORT`
- `TRANSLATE_SERVICE_HOST`, `TRANSLATE_SERVICE_PORT`
- `TTS_HTTP_URL`, `TTS_STREAM_URL`
