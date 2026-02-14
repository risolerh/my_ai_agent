import asyncio
import json
import os
from datetime import datetime
from typing import Optional, Callable, Awaitable, Dict, Any, List

import websockets

TTS_STREAM_URL = os.getenv("TTS_STREAM_URL", "ws://localhost:8000/ws/tts-stream")

def _ts():
    return datetime.now().strftime('%H:%M:%S.%f')[:-3]

DEFAULT_BUFFER_SIZE = 1
LOW_BITRATE_SAMPLE_RATE = 12000
LOW_LATENCY_MODE = "balanced" # low, balanced, high


class TTSStreamClient:
    def __init__(
        self,
        url: str = TTS_STREAM_URL,
        language: str = "en",
        voice: Optional[str] = None,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        low_bitrate: bool = True,
        audio_format: str = "opus", # opus or wav
        on_event: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ):
        self.url = url
        self.language = language
        self.voice = voice
        self.buffer_size = buffer_size
        self.low_bitrate = low_bitrate
        self.audio_format = audio_format
        self.on_event = on_event

        self.available_voices: List[str] = []
        self._ws = None
        self._recv_task: Optional[asyncio.Task] = None
        self._send_lock = asyncio.Lock()

    async def connect(self):
        print(f"[{_ts()}] [TTS-CLIENT] connecting to {self.url}")
        self._ws = await websockets.connect(self.url)
        greeting = await self._ws.recv()
        data = json.loads(greeting)
        voices = (
            data.get("available_voices")
            or data.get("availableVoices")
            or data.get("voices")
            or []
        )
        self.available_voices = voices
        print(f"[{_ts()}] [TTS-CLIENT] voices available: {self.available_voices}")

        if self.on_event:
            await self.on_event({
                "type": "ready",
                "available_voices": self.available_voices,
                "voice": self.voice
            })

        config = {
            "type": "config",
            "language": self.voice or self.language,
            "buffer_size": self.buffer_size,
            "format": self.audio_format
        }
        if self.low_bitrate:
            config["sample_rate"] = LOW_BITRATE_SAMPLE_RATE
            config["bitrate"] = LOW_BITRATE_SAMPLE_RATE
            config["latency_mode"] = LOW_LATENCY_MODE
            config["temperature"] = 0.4
            config["max_chars"] = 100

        print(f"[{_ts()}] [TTS-CLIENT] sending config: {config}")
        await self._send(config)

        self._recv_task = asyncio.create_task(self._recv_loop())

    async def _recv_loop(self):
        try:
            while True:
                msg = await self._ws.recv()
                data = json.loads(msg)
                if self.on_event:
                    await self.on_event(data)
        except Exception:
            pass

    async def send_text(self, text: str):
        if not text:
            return
        await self._send({
            "type": "text",
            "content": text
        })

    async def stop(self):
        await self._send({
            "type": "stop"
        })

    async def _send(self, payload: Dict[str, Any]):
        if not self._ws:
            return
        async with self._send_lock:
            await self._ws.send(json.dumps(payload))

    async def close(self):
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
