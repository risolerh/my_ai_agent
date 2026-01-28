from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from service.audio_service import AudioService
from modules.model_selector import ensure_model, get_models_info, AVAILABLE_MODELS, MODELS_DIR
from service.ollama_client import OllamaClient
from service.tts_stream_service import TTSStreamService
import requests
import asyncio
import os
from typing import Optional

app = FastAPI()

# Configuration
# MODELS_DIR and VOSK_MODELS are replaced by dynamic lookup from AVAILABLE_MODELS
# Note: VOSK_MODELS variable is removed as we use AVAILABLE_MODELS directly now.
TRANSLATION_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese"
}

TTS_HTTP_URL = os.getenv("TTS_HTTP_URL", "http://localhost:8001")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="www/static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse('www/index.html')

@app.get("/favicon.ico")
async def favicon():
    return FileResponse('www/static/favicon.ico')

@app.get("/api/models")
async def get_models():
    """Returns available input (STT) models with download status."""
    return get_models_info()

@app.get("/api/languages")
async def get_languages():
    """Returns supported output (translation) languages."""
    return [{"code": k, "name": v} for k, v in TRANSLATION_LANGUAGES.items()]

@app.get("/api/ollama-models")
async def get_ollama_models():
    """Returns Ollama models available for the agent."""
    return {"models": OLLAMA_MODELS, "default": DEFAULT_OLLAMA_MODEL}

@app.get("/api/tts-voices")
async def get_tts_voices():
    """Returns available TTS voices from the TTS service."""
    try:
        response = requests.get(f"{TTS_HTTP_URL}/voices", timeout=3)
        if response.status_code == 200:
            data = response.json()
            return {"voices": data.get("voices", [])}
    except Exception as e:
        print(f"TTS voices error: {e}")
    return {"voices": []}

# Global instances cache
translator_cache = {}

# Ollama config
OLLAMA_MODELS = [
    "qwen2.5-coder:14b",
    "ministral-3:14b",
    "gpt-oss:20b-cloud",
    "sam860/LFM2:8b",
]
DEFAULT_OLLAMA_MODEL = OLLAMA_MODELS[0]
ollama_client = OllamaClient()


# Global instances
# Default config
DEFAULT_INPUT_MODEL_ID = "2" # Default to English Complete
DEFAULT_OUTPUT_LANG = os.getenv("OUTPUT_LANG", "es")

print(f"Pre-downloading default model ID {DEFAULT_INPUT_MODEL_ID}...")
default_model_info = AVAILABLE_MODELS.get(DEFAULT_INPUT_MODEL_ID)
if default_model_info:
    ensure_model(os.path.join(MODELS_DIR, default_model_info["name"]))


@app.websocket("/ws/stream")
async def websocket_endpoint(
    websocket: WebSocket,
    input_lang: str = "2",
    output_lang: str = "es",
    agent_enabled: str = "false",
    agent_model: Optional[str] = None,
    voice_enabled: str = "false",
    voice_id: Optional[str] = None
):
    """
    WebSocket endpoint for audio streaming with speech recognition and translation.
    
    Args:
        input_lang: Model ID from AVAILABLE_MODELS (e.g. "1", "2")
        output_lang: Target language code for translation (e.g. "es")
    """
    await websocket.accept()
    loop = asyncio.get_running_loop()
    
    agent_enabled_flag = agent_enabled.lower() in ("1", "true", "yes", "on")
    agent_model_name = agent_model or DEFAULT_OLLAMA_MODEL
    if agent_model_name not in OLLAMA_MODELS:
        agent_model_name = DEFAULT_OLLAMA_MODEL
    voice_enabled_flag = voice_enabled.lower() in ("1", "true", "yes", "on")
    if voice_id == "":
        voice_id = None

    # Initialize audio service
    service = AudioService(
        model_id=input_lang,
        output_lang=output_lang,
        translator_cache=translator_cache,
        default_model_id=DEFAULT_INPUT_MODEL_ID,
        ollama_client=ollama_client,
        agent_enabled=agent_enabled_flag,
        agent_model=agent_model_name
    )
    
    tts_service = None

    try:
        # Setup service (download models, initialize translator)
        await service.setup()
        
        # Define message sender
        async def send_message(msg):
            try:
                await websocket.send_json(msg)
            except Exception as e:
                print(f"Error sending message: {e}")

        if agent_enabled_flag:
            tts_language = voice_id or "default"
            tts_service = TTSStreamService(
                language=tts_language,
                voice=voice_id,
                send_message=send_message
            )

        # Register callbacks
        def on_partial(message):
            asyncio.run_coroutine_threadsafe(send_message(message), loop)
        
        def on_final(message):
            asyncio.run_coroutine_threadsafe(send_message(message), loop)

        def on_agent(message):
            asyncio.run_coroutine_threadsafe(send_message(message), loop)
            if voice_enabled_flag and tts_service and message.get("status") == "ok":
                response_text = message.get("response", "")
                asyncio.run_coroutine_threadsafe(
                    tts_service.send_text(response_text),
                    loop
                )
        
        service.set_on_partial(on_partial)
        service.set_on_final(on_final)
        service.set_on_agent(on_agent)

        await send_message({
            "type": "ready",
            "input_lang": service.input_lang_code,
            "output_lang": output_lang
        })

        if tts_service:
            asyncio.create_task(tts_service.start())
        
        print(f"Ready to process audio stream ({service.input_lang_code} -> {output_lang})...")
        
        # Process incoming audio stream
        while True:
            data = await websocket.receive_bytes()
            await service.process_audio(data)
            
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Connection error: {e}")
    finally:
        service.shutdown()
        if tts_service:
            try:
                await tts_service.close()
            except Exception as e:
                print(f"TTS close error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
