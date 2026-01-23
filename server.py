from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from modules.audio_listener import SpeechProcessor
from modules.translate import EnglishToSpanishTranslator
from service.audio_service import AudioService
from modules.model_selector import ensure_model, get_models_info, AVAILABLE_MODELS, MODELS_DIR
import json
import asyncio
import os
import torch
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

# Global instances cache
translator_cache = {}


# Global instances
# Default config
DEFAULT_INPUT_MODEL_ID = "2" # Default to English Complete
DEFAULT_OUTPUT_LANG = os.getenv("OUTPUT_LANG", "es")

print(f"Pre-downloading default model ID {DEFAULT_INPUT_MODEL_ID}...")
default_model_info = AVAILABLE_MODELS.get(DEFAULT_INPUT_MODEL_ID)
if default_model_info:
    ensure_model(os.path.join(MODELS_DIR, default_model_info["name"]))


@app.websocket("/ws/stream")
async def websocket_endpoint(websocket: WebSocket, input_lang: str = "2", output_lang: str = "es"):
    """
    WebSocket endpoint for audio streaming with speech recognition and translation.
    
    Args:
        input_lang: Model ID from AVAILABLE_MODELS (e.g. "1", "2")
        output_lang: Target language code for translation (e.g. "es")
    """
    await websocket.accept()
    loop = asyncio.get_running_loop()
    
    # Initialize audio service
    service = AudioService(
        model_id=input_lang,
        output_lang=output_lang,
        translator_cache=translator_cache,
        default_model_id=DEFAULT_INPUT_MODEL_ID
    )
    
    try:
        # Setup service (download models, initialize translator)
        await service.setup()
        
        # Define message sender
        async def send_message(msg):
            try:
                await websocket.send_json(msg)
            except Exception as e:
                print(f"Error sending message: {e}")
        
        # Register callbacks
        def on_partial(message):
            asyncio.run_coroutine_threadsafe(send_message(message), loop)
        
        def on_final(message):
            asyncio.run_coroutine_threadsafe(send_message(message), loop)
        
        service.set_on_partial(on_partial)
        service.set_on_final(on_final)
        
        print(f"Ready to process audio stream ({service.input_lang_code} -> {output_lang})...")
        
        # Process incoming audio stream
        while True:
            data = await websocket.receive_bytes()
            await service.process_audio(data)
            
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Connection error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
