import asyncio
import os
import logging
import requests
import base64
from typing import Optional, Dict, Any

from modules.grpc_stt import GrpcSttStrategy
from modules.grpc_translator import GrpcTranslator
from modules.model_selector import AVAILABLE_MODELS, MODELS_DIR

TTS_HTTP_URL = os.getenv("TTS_HTTP_URL", "http://127.0.0.1:8004")

class TranslatorService:
    def __init__(self):
        self.stt_strategies = {}
        self.translators = {}
    
    async def process_audio(
        self, 
        audio_data: bytes, 
        input_lang_id: str, 
        output_lang_code: str, 
        voice_id: str,
        output_format: str = "wav"
    ) -> Dict[str, Any]:
        """
        Orchestrates the full translation pipeline:
        Audio (WAV) -> STT -> Text -> Translate -> Text -> TTS -> Audio
        """
        
        # 1. STT: Convert Audio to Text
        stt_result = await self._perform_stt(audio_data, input_lang_id)
        original_text = stt_result.get("text", "")
        
        if not original_text:
            return {
                "original_text": "",
                "translated_text": "",
                "audio_base64": None,
                "sample_rate": 16000
            }

        # 2. Translation: Text to Text
        translated_text = original_text
        input_lang_code = stt_result.get("lang_code", "en")
        
        if input_lang_code != output_lang_code:
            translated_text = await self._perform_translation(original_text, input_lang_code, output_lang_code)

        # 3. TTS: Text to Audio
        tts_result = await self._perform_tts(translated_text, output_lang_code, voice_id, output_format)
        
        audio_base64 = None
        sample_rate = 16000 # Default fallback
        
        if tts_result:
            audio_base64 = tts_result.get("audio_base64")
            sample_rate = tts_result.get("sample_rate", 24000)

        return {
            "original_text": original_text,
            "translated_text": translated_text,
            "audio_base64": audio_base64,
            "sample_rate": sample_rate
        }

    async def _perform_stt(self, audio_data: bytes, model_id: str) -> Dict[str, str]:
        """
        Uses GrpcSttStrategy to transcribe the audio. 
        Since GrpcSttStrategy is streaming-based, we'll wrap it to handle a single file.
        """
        from datetime import datetime
        print(f"[{datetime.now().isoformat()}] [TranslatorService] Starting STT. Data size: {len(audio_data)} bytes. Model: {model_id}")
        
        if model_id not in AVAILABLE_MODELS:
            print(f"[{datetime.now().isoformat()}] [TranslatorService] Model {model_id} not found, defaulting to '2'")
            model_id = "2" # Fallback

        model_info = AVAILABLE_MODELS[model_id]
        model_path = os.path.join(MODELS_DIR, model_info["name"])
        
        loop = asyncio.get_running_loop()
        final_result_future = loop.create_future()
        partial_results = []
        
        stt = GrpcSttStrategy(
            strategy="vosk",
            model_path=model_path
        )
        
        # Initialize (connects to gRPC)
        print(f"[{datetime.now().isoformat()}] [TranslatorService] Initializing GrpcSttStrategy with {model_path}")
        await asyncio.to_thread(stt.initialize, model_path, 16000)
        
        def on_final(text: str, confidence: float):
            print(f"[{datetime.now().isoformat()}] [TranslatorService] STT on_final triggered: '{text}' ({confidence})")
            if not final_result_future.done():
                loop.call_soon_threadsafe(final_result_future.set_result, text)
        
        def on_partial(text: str):
             # Just debug log partials to see if it's "hearing" anything
             if text:
                 print(f"[{datetime.now().isoformat()}] [TranslatorService] STT Partial: {text}")
                 partial_results.append(text)

        stt.set_on_final(on_final)
        stt.set_on_partial(on_partial)
        
        # Send chunks
        chunk_size = 4000
        total_chunks = len(audio_data) // chunk_size + 1
        print(f"[{datetime.now().isoformat()}] [TranslatorService] Sending {total_chunks} chunks...")
        
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i+chunk_size]
            await asyncio.to_thread(stt.process, chunk)
            await asyncio.sleep(0.002) # Tiny sleep to avoid flooding
            
        print(f"[{datetime.now().isoformat()}] [TranslatorService] All chunks sent. Sending silence to flush...")
        
        # Flush/End logic
        silence = bytes(32000) # 1 sec silence (16000 * 2 bytes)
        await asyncio.to_thread(stt.process, silence)
        await asyncio.to_thread(stt.process, silence)
        
        try:
            # Wait for result with a timeout
            print(f"[{datetime.now().isoformat()}] [TranslatorService] Waiting for final result...")
            text = await asyncio.wait_for(final_result_future, timeout=8.0)
            print(f"[{datetime.now().isoformat()}] [TranslatorService] STT Result: {text}")
        except asyncio.TimeoutError:
            print(f"[{datetime.now().isoformat()}] [TranslatorService] STT Timeout - No final result received")
            # Fallback
            if partial_results:
                 print(f"[{datetime.now().isoformat()}] [TranslatorService] Using last partial as fallback: {partial_results[-1]}")
                 text = partial_results[-1]
            else:
                 text = ""
        finally:
            print(f"[{datetime.now().isoformat()}] [TranslatorService] Closing STT strategy")
            stt.close()

        return {"text": text, "lang_code": model_info.get("code", "en")}

    async def _perform_translation(self, text: str, source_lang: str, target_lang: str) -> str:
        key = f"{source_lang}-{target_lang}"
        translator = GrpcTranslator(source_lang=source_lang, target_lang=target_lang)
        # Translator is sync gRPC call
        try:
            result = await asyncio.to_thread(translator.translate, text)
        finally:
             translator.close()
        return result

    async def _perform_tts(self, text: str, language: str, voice_id: str, format: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
            
        payload = {
            "text": text,
            "language": language, 
            "voice": voice_id,
            "format": format
        }
        
        try:
            # Using synchronous requests in thread
            response = await asyncio.to_thread(
                requests.post, 
                f"{TTS_HTTP_URL}/tts", 
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                filename = data.get("filename")
                sr = data.get("sample_rate", 24000)
                
                if filename:
                    file_resp = await asyncio.to_thread(
                        requests.get,
                        f"{TTS_HTTP_URL}/tts/file/{filename}",
                        timeout=10
                    )
                    if file_resp.status_code == 200:
                        b64 = base64.b64encode(file_resp.content).decode("utf-8")
                        return {"audio_base64": b64, "sample_rate": sr}
            
            print(f"TTS Request failed: {response.status_code} {response.text}")
            return None

        except Exception as e:
            print(f"TTS execution failed: {e}")
            return None
