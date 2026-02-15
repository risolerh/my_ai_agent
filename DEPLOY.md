# Despliegue

## Requisitos
- Docker + Docker Compose
- Servicios externos accesibles de STT, Translate y TTS

## Opción recomendada

```bash
docker compose up --build
```

Esto levanta solo el gateway (`service-agent-voice`), que se conecta a STT/Translate/TTS externos.

## Opción local (solo gateway)
Si ya tienes los microservicios corriendo por separado, puedes levantar solo este servicio:

```bash
uv sync
uv run uvicorn server:app --host 0.0.0.0 --port 8000
```

## Opción local (desktop)
Con los mismos servicios gRPC ya corriendo:

```bash
uv sync --extra desktop
uv run python main.py
```

Ajusta hosts/puertos con variables de entorno:
- `STT_SERVICE_HOST`, `STT_SERVICE_PORT`
- `TRANSLATE_SERVICE_HOST`, `TRANSLATE_SERVICE_PORT`
- `TTS_HTTP_URL`, `TTS_STREAM_URL`
