# Dockerized STT & Translation API Implementation

This implementation provides a GPU-accelerated Microservice for Speech-to-Text and Translation using Docker.

## Components
- **server.py**: FastAPI application exposing a WebSocket endpoint.
- **Dockerfile**: Optimized image based on `nvidia/cuda` with Python 3.10.
- **docker-compose.yml**: Orchestrates the service with GPU resource reservation.
- **modules/audio_listener.py**: Refactored to separate speech processing logic (`SpeechProcessor`) from microphone input.

## Prerequisites
- Docker & Docker Compose
- NVIDIA GPU Driver
- **NVIDIA Container Toolkit** (Must be installed to allow Docker to access GPU)
  - [Installation Guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

## Quick Start

### 1. Build and Run
```bash
docker compose up --build
```
*First run will download the Vosk model if not present.*

### 2. Verify
Open http://localhost:8000/ in your browser.
- Click "Start Streaming".
- Allow microphone access.
- Speak into your microphone.
  - You should see partial transcriptions in gray.
  - Final transcriptions (English) and translations (Spanish) will appear in black and blue.

## API Documentation

**WebSocket Endpoint**: `ws://localhost:8000/ws/stream?input_lang={code}&output_lang={code}`
- `input_lang`: Language code for STT (e.g., 'en', 'es'). Default: 'en'.
- `output_lang`: Language code for Translation (e.g., 'es', 'fr'). Default: 'es'.

**Helper Endpoints**:
- `GET /api/models`: Returns list of available input STT models/languages.
- `GET /api/languages`: Returns list of supported output translation languages.

**Input Protocol**:
- Binary messages: Raw PCM Audio
- Format: 16-bit Integer, Little Endian, Monophonic.
- Sample Rate: **16000 Hz** (Must match server config).

**Output Protocol (JSON)**:

**Partial Result**:
```json
{
  "type": "partial",
  "original": "hello world"
}
```

**Final Result**:
```json
{
  "type": "final",
  "original": "hello world",
  "translation": "hola mundo",
  "confidence": 0.95,
  "input_lang": "en",
  "output_lang": "es"
}
```

## Configuration
Environment variables in `docker-compose.yml`:
- `VOSK_MODEL_PATH`: Path to Vosk model (default: `./models/vosk-model-en-us-0.22`)
- `SAMPLE_RATE`: Audio sample rate (default: `16000`)
