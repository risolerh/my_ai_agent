"""
Audio Listener - Captura audio del micrófono y lo procesa con STT.
Usa el patrón Strategy para intercambiar entre diferentes motores STT.
"""
import sounddevice as sd
import queue
import threading
import numpy as np

from typing import Callable, Optional

from .stt import STTStrategy, STTFactory, STTType


class AudioListener:
    """
    Listener de audio que usa el patrón Strategy para STT.
    
    Soporta múltiples estrategias de reconocimiento de voz:
    - Vosk: Tiempo real, baja latencia
    - Whisper: Alta precisión, mayor latencia
    
    Uso:
        # Con Vosk (default)
        listener = AudioListener(
            model_path="./models/vosk-model-en-us-0.22",
            device_id=0
        )
        
        # Con Whisper
        listener = AudioListener(
            model_path="base",  # Tamaño del modelo
            device_id=0,
            stt_type=STTType.WHISPER,
            language="en"
        )
    """
    
    def __init__(
        self,
        model_path: str,
        sample_rate: int = None,  # Auto-detect if None
        block_size: int = None,   # Auto-calculate if None
        channels: int = 1,
        dtype: str = 'int16',
        device_id: int = None,
        latency: float = 0.05,
        stt_type: STTType = STTType.VOSK,
        **stt_kwargs
    ):
        """
        Inicializa el AudioListener.
        
        Args:
            model_path: Ruta al modelo (Vosk) o nombre del modelo (Whisper)
            sample_rate: Sample rate del audio (auto-detecta si es None)
            block_size: Tamaño del bloque de audio (auto-calcula si es None)
            channels: Número de canales (1=mono)
            dtype: Tipo de datos del audio
            device_id: ID del dispositivo de audio
            latency: Latencia deseada en segundos
            stt_type: Tipo de STT a usar (VOSK, WHISPER)
            **stt_kwargs: Argumentos adicionales para la estrategia STT
        """
        self.device_id = device_id
        self.stt_type = stt_type
        
        # Auto-detect sample rate from device
        if sample_rate is None:
            device_info = sd.query_devices(device_id, 'input')
            self.sample_rate = int(device_info['default_samplerate'])
        else:
            self.sample_rate = sample_rate
        
        # Crear estrategia STT usando Factory
        self.strategy: STTStrategy = STTFactory.create(stt_type, **stt_kwargs)
        
        # Inicializar la estrategia
        # Para Whisper, siempre usar 16kHz internamente (resamplear si es necesario)
        strategy_sample_rate = self.sample_rate
        if stt_type == STTType.WHISPER:
            strategy_sample_rate = 16000
        
        self.strategy.initialize(model_path, strategy_sample_rate)
        
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
        
        # Para resampling si es necesario
        self._needs_resampling = (stt_type == STTType.WHISPER and 
                                   self.sample_rate != 16000)

    def set_on_final(self, callback: Callable[[str, float], None]):
        """Callback receives (text, confidence)"""
        self.strategy.set_on_final(callback)

    def set_on_partial(self, callback: Callable[[str], None]):
        self.strategy.set_on_partial(callback)

    def set_on_current(self, callback: Callable[[str], None]):
        self.strategy.set_on_current(callback)
    
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
    
    def _resample(self, audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """Resamplea audio de una tasa a otra."""
        import scipy.signal as signal
        
        audio = np.frombuffer(audio_data, dtype=np.int16)
        
        # Calcular el número de muestras en la nueva tasa
        num_samples = int(len(audio) * to_rate / from_rate)
        
        # Resamplear
        resampled = signal.resample(audio, num_samples)
        
        return resampled.astype(np.int16).tobytes()

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
                while self._running:
                    try:
                        data = self.q.get(timeout=0.5)
                    except:
                        continue
                    
                    # Resamplear si es necesario (para Whisper)
                    if self._needs_resampling:
                        data = self._resample(data, self.sample_rate, 16000)
                    
                    # Procesar con la estrategia STT
                    self.strategy.process(data)

        except Exception as e:
            print(f"Error en listener: {e}")

    def listen_in_thread(self):
        """Inicia la escucha en un hilo separado."""
        self._thread = threading.Thread(target=self.listen, daemon=True)
        self._thread.start()

    def stop(self):
        """Detiene la escucha."""
        self._running = False
        
        # Si es Whisper, forzar procesamiento del buffer pendiente
        if hasattr(self.strategy, 'force_finalize'):
            self.strategy.force_finalize()
        
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=2.0)
            except Exception as e:
                print(f"Error joining thread: {e}")
    
    def reset(self):
        """Reinicia el reconocedor STT."""
        self.strategy.reset()
    
    def get_strategy_name(self) -> str:
        """Retorna el nombre de la estrategia actual."""
        return self.strategy.get_name()
    
    def is_streaming(self) -> bool:
        """Indica si la estrategia actual soporta streaming."""
        return self.strategy.is_streaming()


# Mantener compatibilidad con código anterior
class SpeechProcessor:
    """
    Wrapper de compatibilidad para código legacy.
    
    DEPRECATED: Usar AudioListener con STTStrategy directamente.
    """
    def __init__(self, model_path: str, sample_rate: int):
        from .stt import VoskStrategy
        
        print("[DEPRECATED] SpeechProcessor está deprecado. "
              "Usa AudioListener con estrategias STT.")
        
        self._strategy = VoskStrategy()
        self._strategy.initialize(model_path, sample_rate)
    
    def set_on_final(self, callback):
        self._strategy.set_on_final(callback)
    
    def set_on_partial(self, callback):
        self._strategy.set_on_partial(callback)
    
    def set_on_current(self, callback):
        self._strategy.set_on_current(callback)
    
    def process(self, data: bytes):
        self._strategy.process(data)


if __name__ == "__main__":
    def on_final(text, confidence):
        print(f"\n[FINAL] ({confidence:.2f}): {text}")

    def on_current(text):
        print(text, end="", flush=True)
    
    # Ejemplo con Vosk
    print("=== Prueba con Vosk ===")
    listener = AudioListener(
        model_path="./models/vosk-model-en-us-0.22-lgraph",
        device_id=8,
        stt_type=STTType.VOSK
    )
    
    # Ejemplo con Whisper (comentado)
    # print("=== Prueba con Whisper ===")
    # listener = AudioListener(
    #     model_path="base",
    #     device_id=8,
    #     stt_type=STTType.WHISPER,
    #     language="en"
    # )
    
    listener.set_on_final(on_final)
    listener.set_on_current(on_current)
    
    print(f"Usando: {listener.get_strategy_name()}")
    print(f"Streaming: {listener.is_streaming()}")
    print("Escuchando... Ctrl+C para salir")
    
    listener.listen()