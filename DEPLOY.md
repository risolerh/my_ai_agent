# Despliegue

## Requisitos
- Docker + Docker Compose
- NVIDIA Container Toolkit (si vas a usar GPU en STT/Translate/TTS)

## Opción recomendada

```bash
docker compose up --build
```

Esto levanta el gateway (`service-agent-voice`) y los microservicios gRPC/REST de STT, Translate y TTS.

## Opción local (solo gateway)
Si ya tienes los microservicios corriendo por separado, puedes levantar solo este servicio:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8000
```

## Opción local (desktop)
Con los mismos servicios gRPC ya corriendo:

```bash
python main.py
```

Ajusta hosts/puertos con variables de entorno:
- `STT_SERVICE_HOST`, `STT_SERVICE_PORT`
- `TRANSLATE_SERVICE_HOST`, `TRANSLATE_SERVICE_PORT`
- `TTS_HTTP_URL`, `TTS_STREAM_URL`
