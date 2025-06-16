
import sounddevice as sd
import queue
import vosk
import json
import threading

from typing import Callable, Optional

class AudioListener:
    def __init__(
        self,
        model_path: str,
        sample_rate: int = 32000,
        block_size: int = 4000,
        channels: int = 1,
        dtype: str = 'int16',
        device_id: int = 8 # Default to Voicemeeter Out B1 (VB-Audio Voicemeeter VAIO), MME (8 in, 0 out)
    ):
        self.model = vosk.Model(model_path)
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.channels = channels
        self.dtype = dtype
        self.device_id = device_id
        self.q = queue.Queue()
        self._on_final: Optional[Callable[[str], None]] = None
        self._on_partial: Optional[Callable[[str], None]] = None
        self._on_current: Optional[Callable[[str], None]] = None

    def set_on_final(self, callback: Callable[[str], None]):
        self._on_final = callback

    def set_on_partial(self, callback: Callable[[str], None]):
        self._on_partial = callback

    def set_on_current(self, callback: Callable[[str], None]):
        self._on_current = callback

    def _callback(self, indata, frames, time, status):
        self.q.put(bytes(indata))

    def listen(self):
        with sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            device=self.device_id,
            dtype=self.dtype,
            channels=self.channels,
            callback=self._callback
        ):
            rec = vosk.KaldiRecognizer(self.model, self.sample_rate)
            last_partial = ""
            try:
                while True:
                    data = self.q.get()
                    if rec.AcceptWaveform(data):
                        result = json.loads(rec.Result()).get("text", "")
                        if result and self._on_final:
                            self._on_final(result)
                        last_partial = ""
                    else:
                        partial = json.loads(rec.PartialResult()).get("partial", "")
                        if partial and partial != last_partial:
                            if self._on_partial: 
                                self._on_partial(last_partial)
                            if self._on_current: 
                                self._on_current(partial[len(last_partial):])
                            last_partial = partial
            except KeyboardInterrupt:
                print("\nFinalizado por el usuario.")


    def listen_in_thread(self):
        """Inicia la escucha en un hilo separado."""
        self._thread = threading.Thread(target=self.listen, daemon=True)
        self._thread.start()

    def stop(self):
        """Método para detener la escucha (puedes implementar una bandera si lo necesitas)."""
        # Aquí podrías implementar una bandera para terminar el bucle en listen()
        pass


if __name__ == "__main__":
    def on_final(text):
        print(f"\n[FINAL]: {text}")

    def on_current(text):
        print(text, end="", flush=True)

    # listener = AudioListener("./models/vosk-model-en-us-0.22", device_id=8)
    listener = AudioListener("./models/vosk-model-en-us-0.22-lgraph", device_id=8)
    listener.set_on_final(on_final)
    listener.set_on_current(on_current)
    print("Escuchando... Ctrl+C para salir")
    listener.listen()