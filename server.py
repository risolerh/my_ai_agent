from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from modules.audio_listener import SpeechProcessor
from modules.translate import EnglishToSpanishTranslator
from modules.model_selector import ensure_model
import json
import asyncio
import os
import torch

app = FastAPI()

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

# Global instances
# Use the same default model paths as the desktop app
VOSK_MODEL_PATH = os.getenv("VOSK_MODEL_PATH", "./models/vosk-model-en-us-0.22")
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", 16000))

# Ensure model exists before we start anything
print(f"Ensuring model exists at {VOSK_MODEL_PATH}...")
ensure_model(VOSK_MODEL_PATH)

print("Loading Translator...")
translator = EnglishToSpanishTranslator()
print(f"Translator loaded on {translator.device}")

@app.websocket("/ws/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    loop = asyncio.get_running_loop()
    
    print(f"Client connected. Initializing Vosk model from {VOSK_MODEL_PATH}...")
    try:
        # Initialize processor for this session
        processor = SpeechProcessor(VOSK_MODEL_PATH, SAMPLE_RATE)
        
        async def send_message(msg):
            try:
                await websocket.send_json(msg)
            except Exception as e:
                print(f"Error sending message: {e}")

        def on_final(text, conf):
            # Blocking translation (runs in executor thread)
            try:
                print(f"Final: {text}")
                spanish_text = translator.translate(text)
                msg = {
                    "type": "final",
                    "original": text,
                    "translation": spanish_text,
                    "confidence": conf
                }
                asyncio.run_coroutine_threadsafe(send_message(msg), loop)
            except Exception as e:
                print(f"Translation error: {e}")

        def on_partial(text):
            # msg = {"type": "partial", "original": text}
            # asyncio.run_coroutine_threadsafe(send_message(msg), loop)
            pass

        def on_current(text):
             # For simpler API, maybe just send 'partial' with full text or delta
             # Let's map 'current' (delta) or just use partial logic from Listener
             pass
             
        # Wire callbacks
        # We can implement a more "chatty" partial update if desired
        def on_partial_wrapper(text):
            msg = {"type": "partial", "original": text}
            asyncio.run_coroutine_threadsafe(send_message(msg), loop)

        processor.set_on_final(on_final)
        processor.set_on_partial(on_partial_wrapper)
        
        print("Ready to process audio stream...")
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
