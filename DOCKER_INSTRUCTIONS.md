# Docker Instructions

Este repositorio funciona como **gateway** y depende de microservicios externos (`service-stt`, `service-translate`, `service-tts`).

## Levantar gateway

```bash
docker compose up --build
```

Levanta únicamente:
- `service-agent-voice` (gateway + frontend)

## URLs/puertos esperados
- Agent: `http://localhost:8000`
- STT externo: gRPC `localhost:5002`
- Translate externo: gRPC `localhost:5001`
- TTS externo: REST/WS `localhost:8004` (gRPC opcional `localhost:5003`)

## Verificación rápida
1. Abrir `http://localhost:8000`.
2. Verificar que `GET /api/tts-voices` responda con lista de voces.
3. Iniciar stream en frontend y confirmar eventos `partial`/`final`.

## Configuración por env vars (agent)
- `STT_SERVICE_HOST`, `STT_SERVICE_PORT`
- `TRANSLATE_SERVICE_HOST`, `TRANSLATE_SERVICE_PORT`
- `TTS_HTTP_URL`, `TTS_STREAM_URL`
