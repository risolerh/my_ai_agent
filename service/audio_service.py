import asyncio
import os
import threading
import queue
from datetime import datetime
from typing import Optional, Callable, Dict
from modules.stt.vosk_strategy import VoskStrategy
from modules.translate import EnglishToSpanishTranslator
from modules.model_selector import ensure_model, AVAILABLE_MODELS, MODELS_DIR
from service.ollama_client import OllamaClient

def _ts():
    return datetime.now().strftime('%H:%M:%S.%f')[:-3]

AGENT_HISTORY_LIMIT = 5
TURN_SILENCE_TIMEOUT = 2.5  # seconds of silence before flushing turn to LLM


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
        self.processor: Optional[VoskStrategy] = None
        self.translator: Optional[EnglishToSpanishTranslator] = None
        self.input_lang_code: Optional[str] = None
        self.model_info: Optional[dict] = None
        
        # Callbacks
        self._on_partial: Optional[Callable] = None
        self._on_final: Optional[Callable] = None
        self._on_agent: Optional[Callable] = None
        self._on_barge_in: Optional[Callable] = None
        self._agent_queue: Optional[queue.Queue] = None
        self._agent_thread: Optional[threading.Thread] = None
        self._agent_running = False
        self._agent_cancelled = threading.Event()
        self._agent_history = []

        # Turn accumulator
        self._turn_buffer: list[str] = []
        self._turn_timer: Optional[threading.Timer] = None
        self._turn_lock = threading.Lock()
        self._tts_speaking = False
    
    async def setup(self):
        """
        Async initialization: validate model, download if needed, setup translator.
        Must be called before processing audio.
        """
        # Validate model ID
        if self.model_id not in AVAILABLE_MODELS:
            print(f"[{_ts()}] Invalid model ID: {self.model_id}, defaulting to {self.default_model_id}")
            self.model_id = self.default_model_id
        
        self.model_info = AVAILABLE_MODELS[self.model_id]
        model_path = os.path.join(MODELS_DIR, self.model_info["name"])
        self.input_lang_code = self.model_info.get("code", "en")
        
        print(f"[{_ts()}] Setting up AudioService - Model: {self.model_info['lang']}, Input: {self.input_lang_code}, Output: {self.output_lang}")
        
        # Ensure model exists (download if needed)
        await asyncio.to_thread(ensure_model, model_path)
        
        # Initialize speech processor (Vosk model load can be slow)
        # Initialize speech processor (Vosk Strategy)
        self.processor = await asyncio.to_thread(VoskStrategy)
        await asyncio.to_thread(
            self.processor.initialize,
            model_path,
            self.sample_rate
        )
        
        # Attach callbacks immediately
        self.processor.set_on_final(self._handle_final)
        self.processor.set_on_partial(self._handle_partial)
        
        # Initialize translator if languages differ
        if self.input_lang_code != self.output_lang:
            translator_key = f"{self.input_lang_code}-{self.output_lang}"
            
            if translator_key not in self.translator_cache:
                print(f"[{_ts()}] Initializing translator for {translator_key}...")
                self.translator_cache[translator_key] = await asyncio.to_thread(
                    EnglishToSpanishTranslator, 
                    source_lang=self.input_lang_code, 
                    target_lang=self.output_lang
                )
            
            self.translator = self.translator_cache[translator_key]
        else:
            print(f"[{_ts()}] Same language detected ({self.input_lang_code}), skipping translation")

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

    def set_on_barge_in(self, callback: Callable):
        """
        Set callback for barge-in events (user interrupts TTS).
        Callback signature: callback()
        """
        self._on_barge_in = callback

    def set_tts_speaking(self, speaking: bool):
        """Track whether TTS is currently playing audio."""
        self._tts_speaking = speaking

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

    def barge_in(self):
        """
        Called when user starts speaking while TTS is active.
        Cancels current LLM generation, clears pending work, stops turn timer.
        """
        if not self._tts_speaking:
            return

        print(f"[{_ts()}] [BARGE-IN] User interrupted, cancelling agent + TTS")
        self._tts_speaking = False

        # Cancel turn timer
        with self._turn_lock:
            if self._turn_timer:
                self._turn_timer.cancel()
                self._turn_timer = None
            # Keep buffer contents - they are part of the conversation context

        # Signal agent to abort current generation
        self._agent_cancelled.set()

        # Clear agent queue
        if self._agent_queue:
            try:
                while not self._agent_queue.empty():
                    self._agent_queue.get_nowait()
            except queue.Empty:
                pass

        # Notify caller (server.py) to stop TTS
        if self._on_barge_in:
            self._on_barge_in()

    def _enqueue_agent_prompt(self, prompt_text: str):
        if not self._agent_queue:
            return
        # Reset cancelled flag before new work
        self._agent_cancelled.clear()
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
        # Cancel turn timer
        with self._turn_lock:
            if self._turn_timer:
                self._turn_timer.cancel()
                self._turn_timer = None

        if not self._agent_running:
            return
        self._agent_running = False
        self._agent_cancelled.set()
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

        # Check if cancelled before starting
        if self._agent_cancelled.is_set():
            print(f"[{_ts()}] [AGENT] Cancelled before generation")
            return

        response = self.ollama_client.generate(self.agent_model, full_prompt, False)

        # Check if cancelled after generation (barge-in during LLM call)
        if self._agent_cancelled.is_set():
            print(f"[{_ts()}] [AGENT] Cancelled after generation (barge-in)")
            return
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
    
    def _accumulate_turn(self, text: str):
        """
        Add text to the turn buffer and reset the silence timer.
        The turn is only sent to the LLM after TURN_SILENCE_TIMEOUT seconds
        of silence (no new 'final' results).
        """
        with self._turn_lock:
            self._turn_buffer.append(text)
            
            # Cancel previous timer
            if self._turn_timer:
                self._turn_timer.cancel()
            
            # Start new timer
            self._turn_timer = threading.Timer(
                TURN_SILENCE_TIMEOUT,
                self._flush_turn_buffer
            )
            self._turn_timer.daemon = True
            self._turn_timer.start()
            
            buffer_preview = " ".join(self._turn_buffer)
            print(f"[{_ts()}] [TURN] Accumulated ({len(self._turn_buffer)} parts, {TURN_SILENCE_TIMEOUT}s timer): {buffer_preview[:80]}...")

    def _flush_turn_buffer(self):
        """
        Called when the silence timer expires.
        Combines all accumulated text and sends it to the LLM as one prompt.
        """
        with self._turn_lock:
            if not self._turn_buffer:
                return
            combined_text = " ".join(self._turn_buffer)
            self._turn_buffer.clear()
            self._turn_timer = None
        
        print(f"[{_ts()}] [TURN] Flushing to LLM: {combined_text[:100]}...")
        self._enqueue_agent_prompt(combined_text)

    def _handle_final(self, text: str, confidence: float):
        """Internal handler for final transcriptions."""
        
        
        # Ignore empty or whitespace-only
        if not text or len(text.strip()) == 0:
            return
        # Vosk 'hallucinations' on silence often have 0 confidence and are short stop words
        # Only filter specific known hallucinations to avoid blocking legitimate one-word commands (like "Stop", "Yes")
        hallucinations = {"the", "a", "an", "and", "but", "or", "so", "of", "to"}
        if confidence == 0.0 and text.strip().lower() in hallucinations:
            print(f"[{_ts()}] Ignoring silent hallucination: '{text}'")
            return

        try:
            print(f"[{_ts()}] Final ({self.input_lang_code}): {text}")
            
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
                self._accumulate_turn(prompt_text)
                
        except Exception as e:
            print(f"[{_ts()}] Translation error: {e}")
    
    def _handle_partial(self, text: str):
        """Internal handler for partial transcriptions."""
        # Barge-in: if TTS is speaking and user starts talking, interrupt it
        if self._tts_speaking and text and text.strip():
            self.barge_in()

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
        
        # Process audio in background thread (Vosk is blocking)
        await asyncio.to_thread(self.processor.process, data)
