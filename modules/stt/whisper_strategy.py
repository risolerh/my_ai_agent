"""
Whisper STT Strategy - Implementación de STT usando faster-whisper.
Optimizado para alta precisión con soporte de GPU.
"""
import numpy as np
from typing import Optional, List
from threading import Lock

from .base import STTStrategy, STTResult


class WhisperStrategy(STTStrategy):
    """
    Estrategia STT usando faster-whisper (implementación optimizada de Whisper).
    
    Características:
    - Alta precisión (~50% menos errores que otros modelos)
    - Soporte para 99 idiomas
    - Detección automática de idioma
    - Mejor manejo de ruido y acentos
    
    Nota: No es true streaming, acumula audio y procesa en batches.
    """
    
    # Tamaños de modelo disponibles
    MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3", "turbo"]
    
    def __init__(self, 
                 model_size: str = "base",
                 device: str = "auto",
                 compute_type: str = "auto",
                 language: str = "en"):
        """
        Inicializa la estrategia Whisper.
        
        Args:
            model_size: Tamaño del modelo (tiny, base, small, medium, large-v3, turbo)
            device: Dispositivo (cuda, cpu, auto)
            compute_type: Tipo de cómputo (float16, int8, auto)
            language: Código de idioma (en, es, etc.) o None para autodetección
        """
        super().__init__()
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        
        self.model = None
        self._audio_buffer: List[np.ndarray] = []
        self._buffer_lock = Lock()
        self._min_audio_length = 0.5  # Segundos mínimos para procesar
        self._max_audio_length = 30.0  # Segundos máximos antes de forzar procesamiento
        self._last_text = ""
    
    def initialize(self, model_path: str = None, sample_rate: int = 16000) -> None:
        """
        Inicializa el modelo Whisper.
        
        Args:
            model_path: Puede ser el nombre del modelo o ruta local
            sample_rate: Debe ser 16000 para Whisper
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ImportError(
                "faster-whisper no está instalado. "
                "Instálalo con: pip install faster-whisper"
            )
        
        self._sample_rate = 16000  # Whisper requiere 16kHz
        
        # Usar model_path si se proporciona, sino usar model_size
        model_name = model_path if model_path else self.model_size
        
        # Determinar device y compute_type automáticamente
        device = self.device
        compute_type = self.compute_type
        
        if device == "auto":
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
        
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"
        
        print(f"[Whisper] Cargando modelo '{model_name}' en {device} ({compute_type})...")
        
        self.model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type
        )
        
        print(f"[Whisper] Modelo cargado exitosamente")
    
    def process(self, audio_data: bytes) -> Optional[STTResult]:
        """
        Procesa audio acumulándolo hasta tener suficiente para transcribir.
        
        Whisper no es streaming nativo, así que acumulamos audio
        y procesamos cuando hay suficiente contenido.
        """
        if not self.model:
            raise RuntimeError("Modelo Whisper no inicializado")
        
        # Convertir bytes a numpy array
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        
        with self._buffer_lock:
            self._audio_buffer.append(audio_array)
            
            # Calcular duración total del buffer
            total_samples = sum(len(chunk) for chunk in self._audio_buffer)
            duration = total_samples / self._sample_rate
            
            # Procesar si hay suficiente audio o si excedemos el máximo
            if duration >= self._min_audio_length:
                # Concatenar todo el audio
                full_audio = np.concatenate(self._audio_buffer)
                
                # Si excedemos el máximo, procesar y limpiar
                should_finalize = duration >= self._max_audio_length
                
                # Transcribir
                result = self._transcribe(full_audio, finalize=should_finalize)
                
                if should_finalize:
                    self._audio_buffer.clear()
                    self._last_text = ""
                
                return result
        
        return None
    
    def _transcribe(self, audio: np.ndarray, finalize: bool = False) -> Optional[STTResult]:
        """Realiza la transcripción del audio."""
        try:
            segments, info = self.model.transcribe(
                audio,
                language=self.language,
                beam_size=5,
                vad_filter=True,  # Filtrar silencio
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=200
                )
            )
            
            # Combinar todos los segmentos
            full_text = " ".join(segment.text.strip() for segment in segments)
            
            if not full_text:
                return None
            
            # Calcular confianza promedio
            segments_list = list(self.model.transcribe(
                audio, 
                language=self.language,
                beam_size=5
            )[0])
            
            if segments_list:
                avg_confidence = sum(s.avg_logprob for s in segments_list) / len(segments_list)
                # Convertir log prob a probabilidad aproximada (0-1)
                confidence = min(1.0, max(0.0, 1.0 + avg_confidence))
            else:
                confidence = 0.0
            
            if finalize:
                # Resultado final
                self._emit_final(full_text, confidence)
                return STTResult(
                    text=full_text,
                    confidence=confidence,
                    is_final=True,
                    language=info.language if info else self.language
                )
            else:
                # Resultado parcial - emitir como current
                new_text = full_text[len(self._last_text):]
                if new_text:
                    self._emit_current(new_text)
                self._last_text = full_text
                
                return STTResult(
                    text=full_text,
                    confidence=confidence,
                    is_final=False,
                    language=info.language if info else self.language
                )
                
        except Exception as e:
            print(f"[Whisper] Error en transcripción: {e}")
            return None
    
    def reset(self) -> None:
        """Reinicia el buffer de audio."""
        with self._buffer_lock:
            self._audio_buffer.clear()
            self._last_text = ""
    
    def force_finalize(self) -> Optional[STTResult]:
        """Fuerza el procesamiento del audio acumulado como resultado final."""
        with self._buffer_lock:
            if not self._audio_buffer:
                return None
            
            full_audio = np.concatenate(self._audio_buffer)
            result = self._transcribe(full_audio, finalize=True)
            self._audio_buffer.clear()
            self._last_text = ""
            return result
    
    def get_name(self) -> str:
        return f"Whisper ({self.model_size})"
    
    def is_streaming(self) -> bool:
        # Whisper no es true streaming, pero lo simulamos con buffers
        return False
    
    def set_language(self, language: str) -> None:
        """Cambia el idioma de transcripción."""
        self.language = language
    
    def set_min_audio_length(self, seconds: float) -> None:
        """Configura el tiempo mínimo antes de procesar."""
        self._min_audio_length = max(0.1, seconds)
    
    def set_max_audio_length(self, seconds: float) -> None:
        """Configura el tiempo máximo antes de forzar procesamiento."""
        self._max_audio_length = max(1.0, seconds)
