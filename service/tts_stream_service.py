from typing import Optional, Dict, Any, Callable, Awaitable

from service.tts_stream_client import TTSStreamClient


class TTSStreamService:
    def __init__(
        self,
        language: str,
        voice: Optional[str],
        send_message: Callable[[Dict[str, Any]], Awaitable[None]],
    ):
        self.language = language
        self.voice = voice
        self._send_message = send_message
        self._client: Optional[TTSStreamClient] = None
        self._ready = False
        self._pending_text: Optional[str] = None

    async def start(self):
        try:
            print(f"[TTS-SERVICE] start language={self.language} voice={self.voice}")
            self._client = TTSStreamClient(
                language=self.language,
                voice=self.voice,
                on_event=self._handle_event
            )
            await self._client.connect()
        except Exception as e:
            print(f"[TTS-SERVICE] start error: {e}")
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
            print(f"[TTS-SERVICE] ready voices={len(voices)} selected={data.get('voice')}")
            if self._pending_text and self._client:
                await self._client.send_text(self._pending_text)
                self._pending_text = None
            return

        if msg_type == "audio":
            print(f"[TTS-SERVICE] audio segment={data.get('segment')} sr={data.get('sample_rate')}")
            await self._send_message({
                "type": "tts_audio",
                "segment": data.get("segment"),
                "text": data.get("text", ""),
                "sample_rate": data.get("sample_rate"),
                "data": data.get("data", "")
            })
        elif msg_type == "complete":
            print(f"[TTS-SERVICE] complete total={data.get('total_segments')}")
            await self._send_message({
                "type": "tts_complete",
                "total_segments": data.get("total_segments")
            })
        elif msg_type == "interrupted":
            print(f"[TTS-SERVICE] interrupted segment={data.get('segment')}")
            await self._send_message({
                "type": "tts_interrupted",
                "segment": data.get("segment")
            })

    async def send_text(self, text: str):
        if not text:
            return
        if not self._client or not self._ready:
            self._pending_text = text
            return
        print(f"[TTS-SERVICE] send_text len={len(text)}")
        await self._client.send_text(text)

    async def close(self):
        if self._client:
            await self._client.close()
