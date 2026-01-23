
import sounddevice as sd
import queue
import vosk
import json
import threading
import numpy as np
import os
import requests
import zipfile
import shutil


from typing import Callable, Optional

class SpeechProcessor:
    def __init__(self, model_path: str, sample_rate: int):
        self._ensure_model(model_path)
        abs_model_path = os.path.abspath(model_path)
        self.model = vosk.Model(abs_model_path)
        self.recognizer = vosk.KaldiRecognizer(self.model, sample_rate)
        
        self._on_final: Optional[Callable[[str, float], None]] = None
        self._on_partial: Optional[Callable[[str], None]] = None
        self._on_current: Optional[Callable[[str], None]] = None
        self.last_partial = ""

    def _ensure_model(self, model_path: str):
        """Checks if the model exists, if not, tries to download it."""
        if os.path.exists(model_path) and os.path.isdir(model_path):
            if any(os.scandir(model_path)):
                return
        
        print(f"Model not found at {model_path}. Attempting to download...")
        model_name = os.path.basename(os.path.normpath(model_path))
        base_dir = os.path.dirname(os.path.normpath(model_path))
        
        if base_dir and not os.path.exists(base_dir):
            os.makedirs(base_dir, exist_ok=True)
            
        url = f"https://alphacephei.com/vosk/models/{model_name}.zip"
        print(f"Downloading from {url}...")
        
        try:
            zip_path = os.path.join(base_dir if base_dir else ".", f"{model_name}.zip")
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(zip_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            print("Extracting model...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(base_dir if base_dir else ".")
            os.remove(zip_path)
            print(f"Model '{model_name}' successfully installed.")
        except Exception as e:
            if os.path.exists(zip_path):
                os.remove(zip_path)
            raise RuntimeError(f"Failed to download/install model '{model_name}': {e}")

    def set_on_final(self, callback: Callable[[str, float], None]):
        self._on_final = callback

    def set_on_partial(self, callback: Callable[[str], None]):
        self._on_partial = callback

    def set_on_current(self, callback: Callable[[str], None]):
        self._on_current = callback

    def process(self, data: bytes):
        if self.recognizer.AcceptWaveform(data):
            result_json = json.loads(self.recognizer.Result())
            text = result_json.get("text", "")
            confidence = result_json.get("result", [{}])
            
            if confidence and isinstance(confidence, list):
                confidences = [w.get("conf", 0) for w in confidence if "conf" in w]
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            else:
                avg_confidence = 0.0
            
            if text and self._on_final:
                if avg_confidence >= 0.0:
                    self._on_final(text, avg_confidence)
            self.last_partial = ""
        else:
            partial = json.loads(self.recognizer.PartialResult()).get("partial", "")
            if partial and partial != self.last_partial:
                if self._on_partial: 
                    self._on_partial(self.last_partial)
                if self._on_current: 
                    self._on_current(partial[len(self.last_partial):])
                self.last_partial = partial


class AudioListener:
    def __init__(
        self,
        model_path: str,
        sample_rate: int = None,  # Auto-detect if None
        block_size: int = None,   # Auto-calculate if None
        channels: int = 1,
        dtype: str = 'int16',
        device_id: int = None,
        latency: float = 0.05
    ):
        self.device_id = device_id
        
        # Auto-detect sample rate from device
        if sample_rate is None:
            device_info = sd.query_devices(device_id, 'input')
            self.sample_rate = int(device_info['default_samplerate'])
        else:
            self.sample_rate = sample_rate
            
        # Initialize processor
        self.processor = SpeechProcessor(model_path, self.sample_rate)
        
        # Calculate optimal block size
        if block_size is None:
            self.block_size = int(self.sample_rate * latency)
        else:
            self.block_size = block_size
            
        self.channels = channels
        self.dtype = dtype
        self.q = queue.Queue(maxsize=20)
        self._running = False
        self._on_audio_level: Optional[Callable[[float], None]] = None
        self._thread: Optional[threading.Thread] = None

    def set_on_final(self, callback: Callable[[str, float], None]):
        """Callback receives (text, confidence)"""
        self.processor.set_on_final(callback)

    def set_on_partial(self, callback: Callable[[str], None]):
        self.processor.set_on_partial(callback)

    def set_on_current(self, callback: Callable[[str], None]):
        self.processor.set_on_current(callback)
    
    def set_on_audio_level(self, callback: Callable[[float], None]):
        """Callback receives audio level (0.0-1.0)"""
        self._on_audio_level = callback

    def _callback(self, indata, frames, time, status):
        if self._running:
            # Calculate audio level
            if self._on_audio_level:
                audio_data = np.frombuffer(indata, dtype=np.int16)
                level = np.abs(audio_data).mean() / 32768.0  # Normalize to 0-1
                self._on_audio_level(level)
            
            try:
                self.q.put(bytes(indata), block=False)
            except queue.Full:
                pass  # Drop frame if queue is full

    def listen(self):
        self._running = True
        try:
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                device=self.device_id,
                dtype=self.dtype,
                channels=self.channels,
                callback=self._callback
            ):
                rec = self.processor.recognizer # Use internal recognizer for legacy loop (or update loop)
                # Actually, we should use processor.process()
                
                while self._running:
                    try:
                        data = self.q.get(timeout=0.5)
                    except:
                        continue
                    
                    self.processor.process(data)

        except Exception as e:
            print(f"Error en listener: {e}")


    def listen_in_thread(self):
        """Inicia la escucha en un hilo separado."""
        self._thread = threading.Thread(target=self.listen, daemon=True)
        self._thread.start()

    def stop(self):
        """Detiene la escucha."""
        self._running = False
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=2.0)
            except Exception as e:
                print(f"Error joining thread: {e}")


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