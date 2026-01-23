from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from modules.audio_listener import SpeechProcessor
from modules.translate import EnglishToSpanishTranslator
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
app.mount("/static", StaticFiles(directory="www"), name="static")

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
    input_lang: NOW EXPECTS A MODEL ID (e.g. "1", "2") from AVAILABLE_MODELS.
                Defaults to "2" (English complete) if not found.
    output_lang: Language code for translation (e.g. "es").
    """
    await websocket.accept()
    loop = asyncio.get_running_loop()
    
    # Validate input model (input_lang parameter now acts as model_id)
    model_id = input_lang
    if model_id not in AVAILABLE_MODELS:
        print(f"Invalid model ID: {model_id}, defaulting to {DEFAULT_INPUT_MODEL_ID}")
        model_id = DEFAULT_INPUT_MODEL_ID
    
    model_info = AVAILABLE_MODELS[model_id]
    model_path = os.path.join(MODELS_DIR, model_info["name"])
    input_lang_code = model_info.get("code", "en") # Extract actual language code for specific translation logic
    
    print(f"Client connected. Model ID: {model_id} ({model_info['lang']}), Input Code: {input_lang_code}, Output: {output_lang}")
    
    # Ensure model exists (might block briefly if not downloaded)
    await asyncio.to_thread(ensure_model, model_path)
    
    # Get or Initialize Translator
    translator_key = f"{input_lang_code}-{output_lang}"
    translator = None
    
    if input_lang_code != output_lang:
        if translator_key not in translator_cache:
            print(f"Initializing translator for {translator_key}...")
            # This loads the model, might take time - Run in thread to allow heartbeat
            translator_cache[translator_key] = await asyncio.to_thread(EnglishToSpanishTranslator, source_lang=input_lang_code, target_lang=output_lang)
        translator = translator_cache[translator_key]


    try:
        # Initialize processor for this session
        # SAMPLE_RATE should ideally be negotiated, but we default to 16000
        processor = SpeechProcessor(model_path, 16000)
        
        async def send_message(msg):
            try:
                await websocket.send_json(msg)
            except Exception as e:
                print(f"Error sending message: {e}")

        def on_final(text, conf):
            # Blocking translation (runs in executor thread)
            try:
                print(f"Final ({input_lang_code}): {text}")
                
                spanish_text = text # Default if no translation
                if translator:
                     spanish_text = translator.translate(text)
                
                msg = {
                    "type": "final",
                    "original": text,
                    "translation": spanish_text,
                    "confidence": conf,
                    "input_lang": input_lang_code,
                    "output_lang": output_lang
                }
                asyncio.run_coroutine_threadsafe(send_message(msg), loop)
            except Exception as e:
                print(f"Translation error: {e}")

        def on_partial_wrapper(text):
            msg = {"type": "partial", "original": text}
            asyncio.run_coroutine_threadsafe(send_message(msg), loop)

        processor.set_on_final(on_final)
        processor.set_on_partial(on_partial_wrapper)
        
        print(f"Ready to process audio stream ({input_lang_code} -> {output_lang})...")
        while True:
            data = await websocket.receive_bytes()
            # Run blocking Vosk process in a separate thread
            await asyncio.to_thread(processor.process, data)
            
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Connection error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
