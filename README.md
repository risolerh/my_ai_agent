# Real-time Speech-to-Text & Translation Agent

An intelligent agent capable of transcribing speech in real-time and translating it instantly. This project supports two modes of operation: a standalone Desktop Application with GUI, and a Dockerized WebSocket API for remote streaming.

## 🚀 Features
- **Real-time Transcription (STT)**: Uses [Vosk](https://alphacephei.com/vosk/) for offline, low-latency speech recognition.
- **Instant Translation**: Uses [MarianMT](https://huggingface.co/docs/transformers/model_doc/marian) (Helsinki-NLP) for high-quality translation.
- **GPU Acceleration**: Automatically utilizes NVIDIA GPU (CUDA) for translation if available.
- **Ollama Agent (Optional)**: Envía transcripciones a Ollama para generar respuestas en el front.
- **Dual Modes**: 
    1. **Desktop App**: Graphical interface (Tkinter) for personal use.
    2. **API Server**: WebSocket server for providing STT/Translation services to other apps.

---

## 🖥️ Mode 1: Desktop Application (Local)
Run the application with a graphical user interface (GUI) on your local machine.

### Prerequisites and Installation
For detailed instructions on how to install system dependencies, create a virtual environment, and install configuration, please refer to:

👉 **[DEPLOY.md](./DEPLOY.md)**

### Running the App
```bash
python main.py
```
- A window will open.
- Select your **Microphone** and **Vosk Model** (it will auto-download if missing).
- Click **Start** to begin transcribing and translating.

---

## 🐳 Mode 2: API Server (Docker / Headless)
Expose the functionality as a WebSocket API, ideal for microservices or web integrations.

### Prerequisites and Installation
For detailed instructions on how to install system dependencies, create a virtual environment, and install configuration, please refer to:

👉 **[DEPLOY.md](./DEPLOY.md)**

### Option A: Running with Docker (Recommended)
This method ensures all dependencies are isolated and sets up GPU support automatically.

👉 **[See DOCKER_INSTRUCTIONS.md for full details](./DOCKER_INSTRUCTIONS.md)**

### Option B: Running Locally (Python)
If you have the environment set up locally (from Mode 1), you can run the server directly:

```bash
pkill -f "python server.py" && python server.py
```

Then visit **http://localhost:8000/** to verify operation with the built-in test client.

---

## 📂 Project Structure
- `main.py`: Punto de entrada para la **Versión de Escritorio**. Inicia la interfaz gráfica y conecta los módulos de audio y traducción.
- `server.py`: Punto de entrada para la **Versión Servidor (API)**. Levanta un servidor WebSocket para permitir transcripción y traducción remota.
- `DEPLOY.md` / `DOCKER_INSTRUCTIONS.md`: Guías de instalación y despliegue del proyecto.

### 📂 service/ (Servicios)
- `audio_service.py`: Servicio de procesamiento de audio para el servidor WebSocket.
- `ollama_client.py`: Cliente HTTP para Ollama (agent responses).

### 📂 view/ (Capa de Presentación)
- `page.py`: Interfaz Gráfica de Usuario (GUI) con `tkinter`.

### 📂 modules/ (Lógica Principal)
- `audio_listener.py`: Captura audio en tiempo real y procesa voz a texto (STT) usando Vosk.
- `audio_selector.py`: Maneja la selección de dispositivos de entrada de audio.
- `model_selector.py`: Gestiona la descarga y selección de modelos Vosk.
- `translate.py`: Lógica de traducción usando modelos MarianMT (Helsinki-NLP).
- `logger.py`: Utilidad para registro de logs.

### 📂 Otros Directorios
- `models/`: Almacena los modelos de IA descargados.
- `utils/`: Scripts de utilidad (`listener_test.py`, etc.).
- `www/`: Archivos estáticos para la interfaz web del servidor.
- `docker-compose.yml`: Configuración para orquestación con Docker.
