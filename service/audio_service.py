import asyncio
import os
import threading
import queue
from typing import Optional, Callable, Dict
from modules.audio_listener import SpeechProcessor
from modules.translate import EnglishToSpanishTranslator
from modules.model_selector import ensure_model, AVAILABLE_MODELS, MODELS_DIR
from service.ollama_client import OllamaClient

AGENT_HISTORY_LIMIT = 5


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
        sample_rate: int = 16000,
        ollama_client: Optional[OllamaClient] = None,
        agent_enabled: bool = False,
        agent_model: Optional[str] = None
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
        self.ollama_client = ollama_client
        self.agent_enabled = agent_enabled
        self.agent_model = agent_model
        
        # State
        self.processor: Optional[SpeechProcessor] = None
        self.translator: Optional[EnglishToSpanishTranslator] = None
        self.input_lang_code: Optional[str] = None
        self.model_info: Optional[dict] = None
        
        # Callbacks
        self._on_partial: Optional[Callable] = None
        self._on_final: Optional[Callable] = None
        self._on_agent: Optional[Callable] = None
        self._agent_queue: Optional[queue.Queue] = None
        self._agent_thread: Optional[threading.Thread] = None
        self._agent_running = False
        self._agent_history = []
    
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
        
        # Initialize speech processor (Vosk model load can be slow)
        self.processor = await asyncio.to_thread(
            SpeechProcessor,
            model_path,
            self.sample_rate
        )
        
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

        if self.agent_enabled and self.ollama_client and self.agent_model:
            self._start_agent_worker()
    
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

    def set_on_agent(self, callback: Callable):
        """
        Set callback for agent responses.
        Callback signature: callback(message: dict)
        """
        self._on_agent = callback

    def _start_agent_worker(self):
        if self._agent_running:
            return
        self._agent_queue = queue.Queue(maxsize=1)
        self._agent_running = True
        self._agent_thread = threading.Thread(
            target=self._agent_worker,
            daemon=True
        )
        self._agent_thread.start()

    def _agent_worker(self):
        if not self._agent_queue:
            return
        while self._agent_running:
            try:
                prompt_text = self._agent_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if prompt_text is None:
                continue
            self._run_agent(prompt_text)

    def _enqueue_agent_prompt(self, prompt_text: str):
        if not self._agent_queue:
            return
        try:
            self._agent_queue.put_nowait(prompt_text)
        except queue.Full:
            try:
                _ = self._agent_queue.get_nowait()
            except queue.Empty:
                return
            try:
                self._agent_queue.put_nowait(prompt_text)
            except queue.Full:
                return

    def shutdown(self):
        if not self._agent_running:
            return
        self._agent_running = False
        if self._agent_queue:
            try:
                self._agent_queue.put_nowait(None)
            except queue.Full:
                pass
        if self._agent_thread:
            self._agent_thread.join(timeout=1.0)

    def _run_agent(self, prompt_text: str):
        if not self.ollama_client or not self.agent_enabled or not prompt_text:
            return
        if not self.agent_model:
            return

        if not self.ollama_client.is_available():
            if self._on_agent:
                self._on_agent({
                    "type": "agent",
                    "status": "error",
                    "model": self.agent_model,
                    "error": "Ollama server not available"
                })
            return

        full_prompt = self._format_agent_prompt(prompt_text)
        response = self.ollama_client.generate(self.agent_model, full_prompt, False)
        if not response:
            if self._on_agent:
                self._on_agent({
                    "type": "agent",
                    "status": "error",
                    "model": self.agent_model,
                    "error": "No response from model"
                })
            return

        if self._on_agent:
            self._on_agent({
                "type": "agent",
                "status": "ok",
                "model": self.agent_model,
                "prompt": prompt_text,
                "response": response
            })
        self._agent_history.append({
            "transcript": prompt_text,
            "response": response
        })
        if len(self._agent_history) > AGENT_HISTORY_LIMIT:
            self._agent_history = self._agent_history[-AGENT_HISTORY_LIMIT:]

    def _format_agent_prompt(self, current_text: str) -> str:
        system_prompt = [
            "System:",
            "Always respond in a friendly tone.",
            "Keep responses short.",
            "Use only plain text (no markdown).",
            "Respond in the same language as the user input.",
        ]
        if not self._agent_history:
            return "\n".join(system_prompt + ["New transcription:", current_text])
        lines = system_prompt + ["Context (latest transcriptions and responses):"]
        for item in self._agent_history[-AGENT_HISTORY_LIMIT:]:
            lines.append(f"Transcription: {item['transcript']}")
            lines.append(f"Response: {item['response']}")
        lines.append("New transcription:")
        lines.append(current_text)
        return "\n".join(lines)
    
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

            if self.agent_enabled and self.ollama_client and self._on_agent:
                prompt_text = text or translated_text
                self._enqueue_agent_prompt(prompt_text)
                
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
