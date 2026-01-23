import asyncio
import os
from typing import Optional, Callable, Dict
from modules.audio_listener import SpeechProcessor
from modules.translate import EnglishToSpanishTranslator
from modules.model_selector import ensure_model, AVAILABLE_MODELS, MODELS_DIR


class AudioService:
    """
    Service layer for audio processing, speech recognition, and translation.
    Encapsulates the business logic for WebSocket streaming endpoints.
    """
    
    def __init__(
        self, 
        model_id: str, 
        output_lang: str,
        translator_cache: Dict[str, EnglishToSpanishTranslator],
        default_model_id: str = "2",
        sample_rate: int = 16000
    ):
        """
        Initialize the audio service.
        
        Args:
            model_id: Model ID from AVAILABLE_MODELS
            output_lang: Target language code for translation (e.g., 'es')
            translator_cache: Shared cache for translator instances
            default_model_id: Fallback model ID if provided ID is invalid
            sample_rate: Audio sample rate in Hz
        """
        self.model_id = model_id
        self.output_lang = output_lang
        self.translator_cache = translator_cache
        self.default_model_id = default_model_id
        self.sample_rate = sample_rate
        
        # State
        self.processor: Optional[SpeechProcessor] = None
        self.translator: Optional[EnglishToSpanishTranslator] = None
        self.input_lang_code: Optional[str] = None
        self.model_info: Optional[dict] = None
        
        # Callbacks
        self._on_partial: Optional[Callable] = None
        self._on_final: Optional[Callable] = None
    
    async def setup(self):
        """
        Async initialization: validate model, download if needed, setup translator.
        Must be called before processing audio.
        """
        # Validate model ID
        if self.model_id not in AVAILABLE_MODELS:
            print(f"Invalid model ID: {self.model_id}, defaulting to {self.default_model_id}")
            self.model_id = self.default_model_id
        
        self.model_info = AVAILABLE_MODELS[self.model_id]
        model_path = os.path.join(MODELS_DIR, self.model_info["name"])
        self.input_lang_code = self.model_info.get("code", "en")
        
        print(f"Setting up AudioService - Model: {self.model_info['lang']}, Input: {self.input_lang_code}, Output: {self.output_lang}")
        
        # Ensure model exists (download if needed)
        await asyncio.to_thread(ensure_model, model_path)
        
        # Initialize speech processor
        self.processor = SpeechProcessor(model_path, self.sample_rate)
        
        # Initialize translator if languages differ
        if self.input_lang_code != self.output_lang:
            translator_key = f"{self.input_lang_code}-{self.output_lang}"
            
            if translator_key not in self.translator_cache:
                print(f"Initializing translator for {translator_key}...")
                self.translator_cache[translator_key] = await asyncio.to_thread(
                    EnglishToSpanishTranslator, 
                    source_lang=self.input_lang_code, 
                    target_lang=self.output_lang
                )
            
            self.translator = self.translator_cache[translator_key]
        else:
            print(f"Same language detected ({self.input_lang_code}), skipping translation")
    
    def set_on_partial(self, callback: Callable):
        """
        Set callback for partial transcriptions.
        Callback signature: callback(message: dict)
        """
        self._on_partial = callback
    
    def set_on_final(self, callback: Callable):
        """
        Set callback for final transcriptions with translations.
        Callback signature: callback(message: dict)
        """
        self._on_final = callback
    
    def _handle_final(self, text: str, confidence: float):
        """Internal handler for final transcriptions."""
        try:
            print(f"Final ({self.input_lang_code}): {text}")
            
            translated_text = text  # Default to original if no translation
            if self.translator:
                translated_text = self.translator.translate(text)
            
            message = {
                "type": "final",
                "original": text,
                "translation": translated_text,
                "confidence": confidence,
                "input_lang": self.input_lang_code,
                "output_lang": self.output_lang
            }
            
            if self._on_final:
                self._on_final(message)
                
        except Exception as e:
            print(f"Translation error: {e}")
    
    def _handle_partial(self, text: str):
        """Internal handler for partial transcriptions."""
        message = {
            "type": "partial",
            "original": text
        }
        
        if self._on_partial:
            self._on_partial(message)
    
    async def process_audio(self, data: bytes):
        """
        Process incoming audio data.
        
        Args:
            data: Raw audio bytes (PCM 16-bit)
        """
        if not self.processor:
            raise RuntimeError("AudioService not initialized. Call setup() first.")
        
        # Setup callbacks if not already done
        if not self.processor._on_final:
            self.processor.set_on_final(self._handle_final)
        if not self.processor._on_partial:
            self.processor.set_on_partial(self._handle_partial)
        
        # Process audio in background thread (Vosk is blocking)
        await asyncio.to_thread(self.processor.process, data)
