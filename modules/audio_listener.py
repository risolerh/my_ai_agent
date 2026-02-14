"""Desktop audio listener that streams microphone audio to gRPC STT."""

import queue
import threading
import traceback
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from modules.grpc_stt import GrpcSttStrategy


class AudioListener:
    def __init__(
        self,
        model_path: str,
        sample_rate: int = None,
        block_size: int = None,
        channels: int = 1,
        dtype: str = "int16",
        device_id: int = None,
        latency: float = 0.05,
    ):
        self.device_id = device_id
        self.model_path = model_path

        if sample_rate is None:
            device_info = sd.query_devices(device_id, "input")
            self.sample_rate = int(device_info["default_samplerate"])
        else:
            self.sample_rate = sample_rate

        self.block_size = block_size if block_size is not None else int(self.sample_rate * latency)
        self.channels = channels
        self.dtype = dtype

        self.q: queue.Queue[bytes] = queue.Queue(maxsize=20)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._on_audio_level: Optional[Callable[[float], None]] = None

        self.strategy = GrpcSttStrategy(strategy="vosk", model_path=model_path)
        self.strategy.initialize(model_path=model_path, sample_rate=self.sample_rate)

    def set_on_final(self, callback: Callable[[str, float], None]):
        self.strategy.set_on_final(callback)

    def set_on_partial(self, callback: Callable[[str], None]):
        self.strategy.set_on_partial(callback)

    def set_on_current(self, callback: Callable[[str], None]):
        self.strategy.set_on_current(callback)

    def set_on_audio_level(self, callback: Callable[[float], None]):
        self._on_audio_level = callback

    def _callback(self, indata, frames, time, status):
        if not self._running:
            return

        if self._on_audio_level:
            try:
                audio_data = np.frombuffer(indata, dtype=np.int16)
                level = float(np.abs(audio_data).mean() / 32768.0)
                self._on_audio_level(level)
            except RuntimeError as e:
                # Expected while UI is closing
                if "main thread is not in main loop" not in str(e):
                    print(f"Runtime error in audio callback: {e}")
            except Exception:
                print("Unexpected error in audio callback:")
                traceback.print_exc()

        try:
            self.q.put(bytes(indata), block=False)
        except queue.Full:
            pass

    def listen(self):
        self._running = True
        try:
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                device=self.device_id,
                dtype=self.dtype,
                channels=self.channels,
                callback=self._callback,
            ):
                while self._running:
                    try:
                        data = self.q.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    self.strategy.process(data)
        except KeyboardInterrupt:
            print("Interrupción recibida en listener. Cerrando sesión...")
        except Exception as e:
            print(f"Error en listener: {e}")
            traceback.print_exc()
        finally:
            self._running = False

    def listen_in_thread(self):
        self._thread = threading.Thread(target=self.listen, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        try:
            self.strategy.close()
        except Exception:
            pass
