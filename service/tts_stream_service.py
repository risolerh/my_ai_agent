from typing import Optional, Dict, Any, Callable, Awaitable
import asyncio
import logging
from datetime import datetime

from service.tts_stream_client import TTSStreamClient
from modules.flow_logger import FlowLogger

def _ts():
    return datetime.now().strftime('%H:%M:%S.%f')[:-3]


class TTSStreamService:
    def __init__(
        self,
        language: str,
        voice: Optional[str],
        send_message: Callable[[Dict[str, Any]], Awaitable[None]],
        flow_logger: Optional[FlowLogger] = None,
    ):
        self.language = language
        self.voice = voice
        self._send_message = send_message
        self.flow_logger = flow_logger
        self._client: Optional[TTSStreamClient] = None
        self._ready = False
        self._pending_text: Optional[str] = None
        self._is_speaking = False
        self._on_speaking_changed: Optional[Callable] = None
        # Track what the user actually heard
        self._current_full_response: str = ""
        self._spoken_segments: list[str] = []

    def _flow(self, event: str, level: int = logging.INFO, **fields):
        if not self.flow_logger:
            return
        try:
            self.flow_logger.event(event, level=level, **fields)
        except Exception:
            pass

    async def start(self):
        try:
            print(f"[{_ts()}] [TTS-SERVICE] start language={self.language} voice={self.voice}")
            self._flow("tts.start", language=self.language, voice=self.voice)
            self._client = TTSStreamClient(
                language=self.language,
                voice=self.voice,
                on_event=self._handle_event
            )
            await self._client.connect()
        except Exception as e:
            print(f"[{_ts()}] [TTS-SERVICE] start error: {e}")
            self._flow("tts.start_error", level=logging.ERROR, error=str(e))
            await self._send_message({
                "type": "tts_error",
                "error": str(e)
            })

    async def _handle_event(self, data: Dict[str, Any]):
        msg_type = data.get("type")
        if msg_type == "ready":
            self._ready = True
            voices = (
                data.get("available_voices")
                or data.get("availableVoices")
                or data.get("voices")
                or []
            )
            await self._send_message({
                "type": "tts_voices",
                "voices": voices,
                "voice": data.get("voice")
            })
            print(f"[{_ts()}] [TTS-SERVICE] ready voices={len(voices)} selected={data.get('voice')}")
            self._flow("tts.ready", voices_count=len(voices), selected_voice=data.get("voice"))
            if self._pending_text and self._client:
                await self._client.send_text(self._pending_text)
                self._pending_text = None
            return

        if msg_type == "audio":
            segment_text = data.get("text", "")
            print(f"[{_ts()}] [TTS-SERVICE] audio segment={data.get('segment')} sr={data.get('sample_rate')} text='{segment_text[:50]}'")
            self._flow(
                "tts.audio_segment",
                segment=data.get("segment"),
                sample_rate=data.get("sample_rate"),
                text_len=len(segment_text or ""),
            )
            # Track what the user actually heard
            if segment_text:
                self._spoken_segments.append(segment_text)
            await self._send_message({
                "type": "tts_audio",
                "segment": data.get("segment"),
                "text": segment_text,
                "sample_rate": data.get("sample_rate"),
                "data": data.get("data", "")
            })
            self._set_speaking(True)
        elif msg_type == "complete":
            print(f"[{_ts()}] [TTS-SERVICE] complete total={data.get('total_segments')}")
            self._flow("tts.complete", total_segments=data.get("total_segments"))
            self._set_speaking(False)
            await self._send_message({
                "type": "tts_complete",
                "total_segments": data.get("total_segments")
            })
        elif msg_type == "interrupted":
            print(f"[{_ts()}] [TTS-SERVICE] interrupted segment={data.get('segment')}")
            self._flow("tts.interrupted", segment=data.get("segment"))
            self._set_speaking(False)
            await self._send_message({
                "type": "tts_interrupted",
                "segment": data.get("segment")
            })

    async def send_text(self, text: str):
        if not text:
            return
        # Reset spoken tracking for new response
        self._current_full_response = text
        self._spoken_segments.clear()
        if not self._client or not self._ready:
            self._pending_text = text
            return
        print(f"[{_ts()}] [TTS-SERVICE] send_text len={len(text)}")
        self._flow("tts.send_text", text_len=len(text))
        await self._client.send_text(text)

    async def close(self):
        if self._client:
            await self._client.close()

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    def set_on_speaking_changed(self, callback: Optional[Callable] = None):
        """Set callback for when speaking state changes. callback(is_speaking: bool)"""
        self._on_speaking_changed = callback

    def _set_speaking(self, speaking: bool):
        if self._is_speaking != speaking:
            self._is_speaking = speaking
            self._flow("tts.speaking_changed", speaking=speaking)
            if self._on_speaking_changed:
                self._on_speaking_changed(speaking)

    def get_spoken_text(self) -> str:
        """Return the text that was actually spoken (heard by user) before interruption."""
        return " ".join(self._spoken_segments)

    def get_full_response(self) -> str:
        """Return the full LLM response that was sent to TTS."""
        return self._current_full_response

    async def barge_in(self):
        """Interrupt TTS playback immediately (user started speaking)."""
        if not self._is_speaking and not self._client:
            return
        spoken = self.get_spoken_text()
        full = self.get_full_response()
        print(f"[{_ts()}] [TTS-SERVICE] barge-in: stopping TTS (spoken={len(spoken)} chars of {len(full)} total)")
        self._flow("tts.barge_in", spoken_len=len(spoken), full_len=len(full))
        self._set_speaking(False)
        if self._client:
            try:
                await self._client.stop()
            except Exception as e:
                print(f"[{_ts()}] [TTS-SERVICE] barge-in stop error: {e}")
        await self._send_message({
            "type": "tts_barge_in"
        })
