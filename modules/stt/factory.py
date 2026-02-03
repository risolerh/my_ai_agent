"""
STT Factory - Factory pattern para crear instancias de estrategias STT.
"""
from enum import Enum
from typing import Dict, Any, Optional, Type

from .base import STTStrategy
from .vosk_strategy import VoskStrategy
from .whisper_strategy import WhisperStrategy


class STTType(Enum):
    """Tipos de STT disponibles."""
    VOSK = "vosk"
    WHISPER = "whisper"


class STTFactory:
    """
    Factory para crear instancias de estrategias STT.
    
    Uso:
        # Crear estrategia Vosk
        strategy = STTFactory.create(STTType.VOSK)
        
        # Crear estrategia Whisper con configuración
        strategy = STTFactory.create(
            STTType.WHISPER, 
            model_size="base",
            language="en"
        )
    """
    
    # Registro de estrategias disponibles
    _strategies: Dict[STTType, Type[STTStrategy]] = {
        STTType.VOSK: VoskStrategy,
        STTType.WHISPER: WhisperStrategy,
    }
    
    @classmethod
    def create(cls, stt_type: STTType, **kwargs) -> STTStrategy:
        """
        Crea una instancia de la estrategia STT especificada.
        
        Args:
            stt_type: Tipo de STT a crear
            **kwargs: Argumentos adicionales para el constructor
            
        Returns:
            Instancia de STTStrategy
            
        Raises:
            ValueError: Si el tipo de STT no está registrado
        """
        if stt_type not in cls._strategies:
            available = [t.value for t in cls._strategies.keys()]
            raise ValueError(
                f"Tipo de STT no soportado: {stt_type}. "
                f"Disponibles: {available}"
            )
        
        strategy_class = cls._strategies[stt_type]
        return strategy_class(**kwargs)
    
    @classmethod
    def create_from_string(cls, type_name: str, **kwargs) -> STTStrategy:
        """
        Crea una estrategia desde un string.
        
        Args:
            type_name: Nombre del tipo ("vosk", "whisper")
            **kwargs: Argumentos adicionales
            
        Returns:
            Instancia de STTStrategy
        """
        try:
            stt_type = STTType(type_name.lower())
        except ValueError:
            available = [t.value for t in STTType]
            raise ValueError(
                f"Tipo de STT desconocido: '{type_name}'. "
                f"Disponibles: {available}"
            )
        
        return cls.create(stt_type, **kwargs)
    
    @classmethod
    def register(cls, stt_type: STTType, strategy_class: Type[STTStrategy]) -> None:
        """
        Registra una nueva estrategia STT.
        
        Permite extender el factory con nuevas implementaciones.
        
        Args:
            stt_type: Tipo identificador
            strategy_class: Clase que implementa STTStrategy
        """
        if not issubclass(strategy_class, STTStrategy):
            raise TypeError(
                f"La clase debe heredar de STTStrategy: {strategy_class}"
            )
        cls._strategies[stt_type] = strategy_class
    
    @classmethod
    def get_available_types(cls) -> list:
        """Retorna lista de tipos STT disponibles."""
        return [t.value for t in cls._strategies.keys()]
    
    @classmethod
    def get_type_info(cls, stt_type: STTType) -> Dict[str, Any]:
        """
        Retorna información sobre un tipo de STT.
        
        Args:
            stt_type: Tipo de STT
            
        Returns:
            Diccionario con información del tipo
        """
        info = {
            STTType.VOSK: {
                "name": "Vosk",
                "streaming": True,
                "latency": "low",
                "accuracy": "medium",
                "requires_gpu": False,
                "description": "Motor STT offline con baja latencia. "
                              "Ideal para aplicaciones en tiempo real."
            },
            STTType.WHISPER: {
                "name": "Whisper",
                "streaming": False,
                "latency": "high",
                "accuracy": "high",
                "requires_gpu": True,  # Recomendado
                "description": "Motor STT de OpenAI con alta precisión. "
                              "Soporta 99 idiomas y es robusto a ruido."
            }
        }
        
        return info.get(stt_type, {})
