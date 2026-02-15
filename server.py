from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from service.audio_service import AudioService
from modules.model_selector import AVAILABLE_MODELS
from service.ollama_client import OllamaClient
from service.tts_stream_service import TTSStreamService
import requests
import asyncio
import os
import uuid
import logging
import json
from datetime import datetime
from typing import Optional
from modules.flow_logger import get_flow_logger

def _ts():
    return datetime.now().strftime('%H:%M:%S.%f')[:-3]

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

TTS_HTTP_URL = os.getenv("TTS_HTTP_URL", "http://127.0.0.1:8004")

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
    return FileResponse('www/static/resources/favicon.ico')

@app.get("/api/models")
async def get_models():
    """
    Returns available input (STT) models.
    Model lifecycle is managed by service_stt, not this gateway.
    """
    return [
        {
            "id": key,
            "name": model["name"],
            "lang": model["lang"],
            "code": model.get("code", "en"),
            "downloaded": True
        }
        for key, model in AVAILABLE_MODELS.items()
    ]

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
        print(f"[{_ts()}] TTS voices error: {e}")
    return {"voices": []}

# removed global translator_cache

# Ollama config
OLLAMA_MODELS = []
ollama_client = OllamaClient()
try:
    fetched_models = ollama_client.list_models()
    if fetched_models:
        OLLAMA_MODELS = fetched_models
except Exception as e:
    print(f"[{_ts()}] Failed to fetch models from Ollama: {e}")

DEFAULT_OLLAMA_MODEL = OLLAMA_MODELS[0] if OLLAMA_MODELS else ""

# Default config
DEFAULT_INPUT_MODEL_ID = "2" # Default to English Complete
DEFAULT_OUTPUT_LANG = os.getenv("OUTPUT_LANG", "es")

from service.translator_service import TranslatorService
from fastapi import UploadFile, File, Form

translator_service = TranslatorService()

@app.post("/api/translate-audio")
async def translate_audio_endpoint(
    file: UploadFile = File(...),
    input_lang: str = Form("2"),
    output_lang: str = Form("es"),
    voice_id: str = Form(""),
    output_format: str = Form("wav")
):
    """
    Process a full audio file: STT -> Translate -> TTS
    Returns: JSON with original text, translation, and audio base64.
    """
    audio_bytes = await file.read()
    
    result = await translator_service.process_audio(
        audio_data=audio_bytes,
        input_lang_id=input_lang,
        output_lang_code=output_lang,
        voice_id=voice_id,
        output_format=output_format
    )
    
    return result


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
    session_started_at = loop.time()
    session_id = uuid.uuid4().hex[:12]
    flow_logger = get_flow_logger("session", session_id=session_id)
    flow_log_partials = os.getenv("FLOW_LOG_PARTIALS", "").lower() in {"1", "true", "yes", "on"}
    sent_counts = {}
    received_audio_chunks = 0
    received_audio_bytes = 0
    forwarded_partials = 0
    forwarded_finals = 0
    forwarded_agents = 0
    barge_in_count = 0
    close_reason = "unknown"
    
    agent_enabled_flag = agent_enabled.lower() in ("1", "true", "yes", "on")
    agent_model_name = agent_model or DEFAULT_OLLAMA_MODEL
    if agent_model_name not in OLLAMA_MODELS:
        agent_model_name = DEFAULT_OLLAMA_MODEL
    voice_enabled_flag = voice_enabled.lower() in ("1", "true", "yes", "on")
    if voice_id == "":
        voice_id = None

    flow_logger.event(
        "ws.accepted",
        input_model_id=input_lang,
        output_lang=output_lang,
        agent_enabled=agent_enabled_flag,
        agent_model=agent_model_name,
        voice_enabled=voice_enabled_flag,
        voice_id=voice_id,
    )

    # Create a local translator cache for this connection only
    # This ensures a fresh context and model loading for each session
    local_translator_cache = {}

    # Initialize audio service
    service = AudioService(
        model_id=input_lang,
        output_lang=output_lang,
        translator_cache=local_translator_cache,
        default_model_id=DEFAULT_INPUT_MODEL_ID,
        ollama_client=ollama_client,
        agent_enabled=agent_enabled_flag,
        agent_model=agent_model_name,
        flow_logger=get_flow_logger("audio_service", session_id=session_id)
    )
    
    tts_service = None

    try:
        # Setup service (initialize gRPC clients and callbacks)
        await service.setup()
        flow_logger.event("service.ready", input_lang=service.input_lang_code, output_lang=output_lang)
        
        # Define message sender
        async def send_message(msg):
            try:
                msg_type = msg.get("type", "unknown")
                sent_counts[msg_type] = sent_counts.get(msg_type, 0) + 1
                if msg_type in {"ready", "final", "agent", "tts_error", "tts_interrupted", "tts_barge_in", "tts_complete", "conversation_cleared"}:
                    flow_logger.event("ws.send", type=msg_type, status=msg.get("status"))
                elif msg_type == "agent_chunk" and msg.get("status") in {"start", "done", "cancelled"}:
                    flow_logger.event("ws.send", type=msg_type, status=msg.get("status"))
                elif msg_type == "partial" and flow_log_partials:
                    flow_logger.event("ws.send", level=logging.DEBUG, type=msg_type, text_len=len(msg.get("original", "")))
                await websocket.send_json(msg)
            except Exception as e:
                print(f"[{_ts()}] Error sending message: {e}")
                flow_logger.event("ws.send_error", level=logging.ERROR, error=str(e))

        if agent_enabled_flag:
            tts_language = voice_id or "default"
            tts_service = TTSStreamService(
                language=tts_language,
                voice=voice_id,
                send_message=send_message,
                flow_logger=get_flow_logger("tts_service", session_id=session_id)
            )

        # Register callbacks
        def on_partial(message):
            nonlocal forwarded_partials
            forwarded_partials += 1
            if flow_log_partials:
                flow_logger.event("stt.partial_forwarded", level=logging.DEBUG, text_len=len(message.get("original", "")))
            asyncio.run_coroutine_threadsafe(send_message(message), loop)
        
        def on_final(message):
            nonlocal forwarded_finals
            forwarded_finals += 1
            flow_logger.event(
                "stt.final_forwarded",
                confidence=round(float(message.get("confidence", 0.0)), 3),
                text_len=len(message.get("original", "") or ""),
                translation_len=len(message.get("translation", "") or ""),
            )
            asyncio.run_coroutine_threadsafe(send_message(message), loop)

        def on_agent(message):
            nonlocal forwarded_agents
            forwarded_agents += 1
            flow_logger.event(
                "agent.forwarded",
                status=message.get("status"),
                model=message.get("model"),
                response_len=len(message.get("response", "") or ""),
            )
            asyncio.run_coroutine_threadsafe(send_message(message), loop)
            if voice_enabled_flag and tts_service and message.get("status") == "ok":
                response_text = message.get("response", "")
                asyncio.run_coroutine_threadsafe(
                    tts_service.send_text(response_text),
                    loop
                )

        def on_agent_chunk(message):
            """Forward streaming LLM chunks to frontend in real-time."""
            if message.get("status") in {"start", "done", "cancelled"}:
                flow_logger.event("agent.chunk", status=message.get("status"))
            asyncio.run_coroutine_threadsafe(send_message(message), loop)
        
        def on_barge_in(
            playback_percent: Optional[float] = None,
            played_audio_seconds: Optional[float] = None,
            total_audio_seconds: Optional[float] = None,
            played_text_percent: Optional[float] = None,
        ):
            """Called from AudioService when user interrupts TTS."""
            nonlocal barge_in_count
            barge_in_count += 1
            flow_logger.event("barge_in.triggered", count=barge_in_count)
            spoken_text = ""
            full_response = ""
            if tts_service:
                spoken_text = tts_service.get_spoken_text()
                full_response = tts_service.get_full_response()
                asyncio.run_coroutine_threadsafe(
                    tts_service.barge_in(),
                    loop
                )
            # Tell AudioService what the user actually heard
            service.set_barge_in_context(
                spoken_text,
                full_response,
                playback_percent=playback_percent,
                played_audio_seconds=played_audio_seconds,
                total_audio_seconds=total_audio_seconds,
                played_text_percent=played_text_percent,
            )

        def on_speaking_changed(is_speaking: bool):
            """Called when TTS starts/stops speaking."""
            service.set_tts_speaking(is_speaking)
            flow_logger.event("tts.speaking_changed", speaking=is_speaking)

        service.set_on_partial(on_partial)
        service.set_on_final(on_final)
        service.set_on_agent(on_agent)
        service.set_on_agent_chunk(on_agent_chunk)
        service.set_on_barge_in(on_barge_in)

        if tts_service:
            tts_service.set_on_speaking_changed(on_speaking_changed)

        await send_message({
            "type": "ready",
            "input_lang": service.input_lang_code,
            "output_lang": output_lang
        })

        if tts_service:
            asyncio.create_task(tts_service.start())
        
        print(f"[{_ts()}] Ready to process audio stream ({service.input_lang_code} -> {output_lang})...")
        flow_logger.event("audio.ingest_started")
        
        # Process incoming audio stream
        while True:
            event = await websocket.receive()
            event_type = event.get("type")

            if event_type == "websocket.disconnect":
                raise WebSocketDisconnect()

            text_payload = event.get("text")
            if text_payload is not None:
                try:
                    text_message = json.loads(text_payload)
                except json.JSONDecodeError:
                    flow_logger.event("ws.invalid_text_message", level=logging.WARNING)
                    continue

                msg_type = text_message.get("type")
                if msg_type == "clear_conversation_history":
                    service.clear_conversation_history()
                    flow_logger.event("conversation.cleared_by_client")
                    await send_message({
                        "type": "conversation_cleared"
                    })
                elif msg_type == "barge_in":
                    playback_percent = text_message.get("playback_percent")
                    played_audio_seconds = text_message.get("played_audio_seconds")
                    total_audio_seconds = text_message.get("total_audio_seconds")
                    played_text_percent = text_message.get("played_text_percent")
                    flow_logger.event(
                        "barge_in.client_signal",
                        playback_percent=playback_percent,
                        played_audio_seconds=played_audio_seconds,
                        total_audio_seconds=total_audio_seconds,
                        played_text_percent=played_text_percent,
                    )
                    service.barge_in(
                        playback_percent=playback_percent,
                        played_audio_seconds=played_audio_seconds,
                        total_audio_seconds=total_audio_seconds,
                        played_text_percent=played_text_percent,
                        force=True,
                    )
                else:
                    flow_logger.event("ws.ignored_text_message", type=msg_type)
                continue

            data = event.get("bytes")
            if data is None:
                continue

            received_audio_chunks += 1
            received_audio_bytes += len(data)
            if received_audio_chunks == 1 or received_audio_chunks % 50 == 0:
                flow_logger.event(
                    "audio.ingest_progress",
                    chunks=received_audio_chunks,
                    bytes=received_audio_bytes,
                )
            await service.process_audio(data) # Envía el audio al servicio STT
            
    except WebSocketDisconnect:
        print(f"[{_ts()}] Client disconnected")
        close_reason = "client_disconnected"
        flow_logger.event("ws.disconnected")
    except Exception as e:
        print(f"[{_ts()}] Connection error: {e}")
        close_reason = "error"
        flow_logger.event("ws.error", level=logging.ERROR, error=str(e))
    finally:
        service.shutdown()
        if tts_service:
            try:
                await tts_service.close()
            except Exception as e:
                print(f"[{_ts()}] TTS close error: {e}")
                flow_logger.event("tts.close_error", level=logging.ERROR, error=str(e))
        duration_ms = int((loop.time() - session_started_at) * 1000)
        flow_logger.event(
            "ws.closed",
            reason=close_reason,
            duration_ms=duration_ms,
            audio_chunks=received_audio_chunks,
            audio_bytes=received_audio_bytes,
            partials_forwarded=forwarded_partials,
            finals_forwarded=forwarded_finals,
            agent_messages=forwarded_agents,
            barge_ins=barge_in_count,
            sent_counts=sent_counts,
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
