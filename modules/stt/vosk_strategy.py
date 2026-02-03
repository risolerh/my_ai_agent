"""
Vosk STT Strategy - Implementación de STT usando Vosk.
Optimizado para reconocimiento en tiempo real con baja latencia.
"""
import json
import os
from typing import Optional

import vosk

from .base import STTStrategy, STTResult


class VoskStrategy(STTStrategy):
    """
    Estrategia STT usando Vosk.
    
    Características:
    - Streaming en tiempo real
    - Baja latencia (<100ms)
    - Funciona offline
    - Bajo consumo de recursos
    """
    
    def __init__(self):
        super().__init__()
        self.model: Optional[vosk.Model] = None
        self.recognizer: Optional[vosk.KaldiRecognizer] = None
        self.last_partial: str = ""
    
    def initialize(self, model_path: str, sample_rate: int) -> None:
        """
        Inicializa el modelo Vosk.
        
        Args:
            model_path: Ruta al directorio del modelo Vosk
            sample_rate: Frecuencia de muestreo (típicamente 16000)
        """
        abs_model_path = os.path.abspath(model_path)
        
        if not os.path.exists(abs_model_path):
            raise FileNotFoundError(f"Modelo Vosk no encontrado: {abs_model_path}")
        
        # Suprimir logs de Vosk
        vosk.SetLogLevel(-1)
        
        self.model = vosk.Model(abs_model_path)
        self._sample_rate = sample_rate
        self.recognizer = vosk.KaldiRecognizer(self.model, sample_rate)
        self.last_partial = ""
        
        print(f"[Vosk] Modelo cargado: {model_path}")
    
    def process(self, audio_data: bytes) -> Optional[STTResult]:
        """
        Procesa audio y retorna transcripción.
        
        Vosk procesa audio en streaming, emitiendo resultados
        parciales y finales a través de callbacks.
        """
        if not self.recognizer:
            raise RuntimeError("Modelo Vosk no inicializado")
        
        if self.recognizer.AcceptWaveform(audio_data):
            # Resultado final
            result_json = json.loads(self.recognizer.Result())
            text = result_json.get("text", "")
            
            # Calcular confianza promedio
            word_results = result_json.get("result", [])
            if word_results and isinstance(word_results, list):
                confidences = [w.get("conf", 0) for w in word_results if "conf" in w]
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            else:
                avg_confidence = 0.0
            
            if text:
                self._emit_final(text, avg_confidence)
                self.last_partial = ""
                return STTResult(
                    text=text,
                    confidence=avg_confidence,
                    is_final=True
                )
        else:
            # Resultado parcial
            partial = json.loads(self.recognizer.PartialResult()).get("partial", "")
            
            if partial and partial != self.last_partial:
                # Emitir la parte anterior como parcial
                self._emit_partial(self.last_partial)
                
                # Emitir solo lo nuevo como current
                new_text = partial[len(self.last_partial):]
                self._emit_current(new_text)
                
                self.last_partial = partial
                
                return STTResult(
                    text=partial,
                    confidence=0.0,
                    is_final=False
                )
        
        return None
    
    def reset(self) -> None:
        """Reinicia el reconocedor para una nueva sesión."""
        if self.recognizer:
            # Crear nuevo recognizer con el mismo modelo
            self.recognizer = vosk.KaldiRecognizer(self.model, self._sample_rate)
            self.last_partial = ""
    
    def get_name(self) -> str:
        return "Vosk"
    
    def is_streaming(self) -> bool:
        return True
    
    def get_final_result(self) -> Optional[STTResult]:
        """Obtiene el resultado final pendiente (útil al terminar)."""
        if not self.recognizer:
            return None
            
        result_json = json.loads(self.recognizer.FinalResult())
        text = result_json.get("text", "")
        
        if text:
            return STTResult(text=text, confidence=0.0, is_final=True)
        return None
