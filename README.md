# Real-time Speech-to-Text & Translation Agent

An intelligent agent capable of transcribing speech in real-time and translating it instantly. This project supports two modes of operation: a standalone Desktop Application with GUI, and a Dockerized WebSocket API for remote streaming.

## 🚀 Features
- **Real-time Transcription (STT)**: Uses [Vosk](https://alphacephei.com/vosk/) for offline, low-latency speech recognition.
- **Instant Translation**: Uses [MarianMT](https://huggingface.co/docs/transformers/model_doc/marian) (Helsinki-NLP) for high-quality translation.
- **GPU Acceleration**: Automatically utilizes NVIDIA GPU (CUDA) for translation if available.
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
python server.py
```

Then visit **http://localhost:8000/** to verify operation with the built-in test client.

---

## 📂 Project Structure
- `main.py`: Entry point for the Desktop GUI.
- `server.py`: Entry point for the FastAPI WebSocket Server.
- `modules/`: Core logic (Audio detection, Translation, GUI).
- `models/`: Directory where Vosk/MarianMT models are stored.
- `docker-compose.yml`: Docker orchestration config.