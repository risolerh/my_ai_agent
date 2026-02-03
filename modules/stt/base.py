"""
Base STT Strategy - Abstract interface for Speech-to-Text implementations.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class STTResult:
    """Resultado de una transcripción STT."""
    text: str
    confidence: float = 0.0
    is_final: bool = False
    language: Optional[str] = None


class STTStrategy(ABC):
    """
    Interfaz abstracta para estrategias de Speech-to-Text.
    Implementa el patrón Strategy para permitir intercambiar
    fácilmente entre diferentes motores STT (Vosk, Whisper, etc.)
    """
    
    def __init__(self):
        self._on_final: Optional[Callable[[str, float], None]] = None
        self._on_partial: Optional[Callable[[str], None]] = None
        self._on_current: Optional[Callable[[str], None]] = None
        self._sample_rate: int = 16000
    
    @property
    def sample_rate(self) -> int:
        """Sample rate requerido por el modelo."""
        return self._sample_rate
    
    @sample_rate.setter
    def sample_rate(self, value: int):
        self._sample_rate = value
    
    @abstractmethod
    def initialize(self, model_path: str, sample_rate: int) -> None:
        """
        Inicializa el modelo STT.
        
        Args:
            model_path: Ruta al modelo o nombre del modelo
            sample_rate: Frecuencia de muestreo del audio
        """
        pass
    
    @abstractmethod
    def process(self, audio_data: bytes) -> Optional[STTResult]:
        """
        Procesa un chunk de audio y retorna el resultado.
        
        Args:
            audio_data: Datos de audio en bytes (int16)
            
        Returns:
            STTResult con la transcripción o None si no hay resultado
        """
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """Reinicia el estado del reconocedor."""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Retorna el nombre de la estrategia."""
        pass
    
    @abstractmethod
    def is_streaming(self) -> bool:
        """Indica si la estrategia soporta streaming en tiempo real."""
        pass
    
    def set_on_final(self, callback: Callable[[str, float], None]) -> None:
        """Callback para texto final confirmado (text, confidence)."""
        self._on_final = callback
    
    def set_on_partial(self, callback: Callable[[str], None]) -> None:
        """Callback para texto parcial (hipótesis anterior)."""
        self._on_partial = callback
    
    def set_on_current(self, callback: Callable[[str], None]) -> None:
        """Callback para texto actual en tiempo real."""
        self._on_current = callback
    
    def _emit_final(self, text: str, confidence: float) -> None:
        """Emite evento de texto final."""
        if self._on_final and text:
            self._on_final(text, confidence)
    
    def _emit_partial(self, text: str) -> None:
        """Emite evento de texto parcial."""
        if self._on_partial and text:
            self._on_partial(text)
    
    def _emit_current(self, text: str) -> None:
        """Emite evento de texto actual."""
        if self._on_current and text:
            self._on_current(text)
