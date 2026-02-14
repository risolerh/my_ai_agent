import asyncio
import os
import threading
import queue
import logging
from datetime import datetime
from typing import Optional, Callable, Dict
from modules.grpc_stt import GrpcSttStrategy
from modules.grpc_translator import GrpcTranslator as EnglishToSpanishTranslator
from modules.model_selector import AVAILABLE_MODELS, MODELS_DIR
from service.ollama_client import OllamaClient
from modules.flow_logger import FlowLogger

def _ts():
    return datetime.now().strftime('%H:%M:%S.%f')[:-3]

AGENT_HISTORY_LIMIT = 5
TURN_SILENCE_TIMEOUT = 4.0  # seconds of silence before flushing turn to LLM


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
        agent_model: Optional[str] = None,
        flow_logger: Optional[FlowLogger] = None
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
        self.flow_logger = flow_logger
        self._flow_log_partials = os.getenv("FLOW_LOG_PARTIALS", "").lower() in {"1", "true", "yes", "on"}
        
        # State
        self.processor: Optional[GrpcSttStrategy] = None
        self.translator: Optional[EnglishToSpanishTranslator] = None
        self.input_lang_code: Optional[str] = None
        self.model_info: Optional[dict] = None
        
        # Callbacks
        self._on_partial: Optional[Callable] = None
        self._on_final: Optional[Callable] = None
        self._on_agent: Optional[Callable] = None
        self._on_agent_chunk: Optional[Callable] = None
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
        self._is_agent_generating = False
        self._current_agent_prompt: Optional[str] = None

        # Barge-in context: what the user actually heard from TTS
        self._barge_in_lock = threading.Lock()
        self._last_spoken_text: str = ""
        self._last_full_response: str = ""
        self._last_partial_text: str = ""
        self._debug_partials = os.getenv("STT_DEBUG_PARTIALS", "").lower() in {"1", "true", "yes", "on"}

    def _flow(self, event: str, level: int = logging.INFO, **fields):
        if not self.flow_logger:
            return
        try:
            self.flow_logger.event(event, level=level, **fields)
        except Exception:
            pass
    
    async def setup(self):
        """
        Async initialization: validate model and setup gRPC clients.
        Must be called before processing audio.
        """
        # Validate model ID
        if self.model_id not in AVAILABLE_MODELS:
            requested_model_id = self.model_id
            print(f"[{_ts()}] Invalid model ID: {self.model_id}, defaulting to {self.default_model_id}")
            self.model_id = self.default_model_id
            self._flow("audio.invalid_model_fallback", requested_model_id=requested_model_id, fallback_model_id=self.default_model_id)
        
        self.model_info = AVAILABLE_MODELS[self.model_id]
        model_path = os.path.join(MODELS_DIR, self.model_info["name"])
        self.input_lang_code = self.model_info.get("code", "en")
        self._flow(
            "audio.setup_start",
            model_id=self.model_id,
            model_name=self.model_info["name"],
            input_lang=self.input_lang_code,
            output_lang=self.output_lang,
        )
        
        print(f"[{_ts()}] Setting up AudioService - Model: {self.model_info['lang']}, Input: {self.input_lang_code}, Output: {self.output_lang}")
        
        # Initialize speech processor (gRPC STT Strategy)
        self.processor = await asyncio.to_thread(
            GrpcSttStrategy,
            strategy="vosk", 
            model_path=model_path
        )
        await asyncio.to_thread(
            self.processor.initialize,
            model_path,
            self.sample_rate
        )
        self._flow(
            "stt.stream_initialized",
            strategy="grpc-vosk",
            sample_rate=self.sample_rate,
        )
        
        # Attach callbacks immediately
        self.processor.set_on_final(self._handle_final)
        self.processor.set_on_partial(self._handle_partial)
        
        # Initialize translator if languages differ
        if self.input_lang_code != self.output_lang:
            translator_key = f"{self.input_lang_code}-{self.output_lang}"
            
            if translator_key not in self.translator_cache:
                print(f"[{_ts()}] Initializing translator for {translator_key}...")
                self.translator_cache[translator_key] = EnglishToSpanishTranslator(
                    source_lang=self.input_lang_code,
                    target_lang=self.output_lang
                )
            
            self.translator = self.translator_cache[translator_key]
            self._flow("translator.ready", pair=translator_key)
        else:
            print(f"[{_ts()}] Same language detected ({self.input_lang_code}), skipping translation")
            self._flow("translator.skipped_same_language", language=self.input_lang_code)

        if self.agent_enabled and self.ollama_client and self.agent_model:
            self._start_agent_worker()
            self._flow("agent.worker_started", model=self.agent_model)
    
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

    def set_barge_in_context(self, spoken_text: str, full_response: str):
        """
        Called by server.py during barge-in to record what the user
        actually heard (spoken_text) vs the full LLM response.
        """
        with self._barge_in_lock:
            self._last_spoken_text = spoken_text
            self._last_full_response = full_response
            print(f"[{_ts()}] [BARGE-IN] User heard: '{spoken_text[:80]}...' of '{full_response[:80]}...'")
            # Save to history: the user heard only part of the response
            if full_response:
                self._agent_history.append({
                    "transcript": "",  # transcript was already saved in normal flow
                    "response": full_response,
                    "interrupted": True,
                    "spoken": spoken_text
                })
                if len(self._agent_history) > AGENT_HISTORY_LIMIT:
                    self._agent_history = self._agent_history[-AGENT_HISTORY_LIMIT:]

    def barge_in(self):
        """
        Called when user starts speaking while TTS is active or Agent is generating.
        Cancels current LLM generation, clears pending work, stops turn timer.
        """
        # Allow barge-in if TTS is speaking OR Agent is generating
        if not self._tts_speaking and not self._is_agent_generating:
            return

        print(f"[{_ts()}] [BARGE-IN] User interrupted, cancelling agent + TTS")
        self._flow(
            "barge_in.triggered",
            tts_speaking=self._tts_speaking,
            agent_generating=self._is_agent_generating,
        )
        # Recover currently processing prompt if any
        recovered_prompt = None
        if self._is_agent_generating and self._current_agent_prompt:
            recovered_prompt = self._current_agent_prompt
            print(f"[{_ts()}] [BARGE-IN] Recovering cancelled prompt: '{recovered_prompt[:50]}...'")

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

        # Re-queue recovered prompt into turn buffer so it's not lost
        if recovered_prompt:
            with self._turn_lock:
                # Prepend to buffer so it comes before the new input that caused the interruption
                self._turn_buffer.insert(0, recovered_prompt)
                print(f"[{_ts()}] [BARGE-IN] Added recovered prompt to buffer. New size: {len(self._turn_buffer)}")
                self._flow("barge_in.prompt_recovered", recovered_len=len(recovered_prompt), buffer_size=len(self._turn_buffer))

        # Notify caller (server.py) to stop TTS and get spoken context
        if self._on_barge_in:
            self._on_barge_in()


    def _enqueue_agent_prompt(self, prompt_text: str):
        if not self._agent_queue:
            return
        # Reset cancelled flag before new work
        self._agent_cancelled.clear()
        try:
            self._agent_queue.put_nowait(prompt_text)
            self._flow("agent.prompt_queued", prompt_len=len(prompt_text), replaced_existing=False)
        except queue.Full:
            try:
                _ = self._agent_queue.get_nowait()
            except queue.Empty:
                return
            try:
                self._agent_queue.put_nowait(prompt_text)
                self._flow("agent.prompt_queued", prompt_len=len(prompt_text), replaced_existing=True)
            except queue.Full:
                return

    def shutdown(self):
        # Cancel turn timer
        with self._turn_lock:
            if self._turn_timer:
                self._turn_timer.cancel()
                self._turn_timer = None
        
        # Release translator resources
        self.translator = None
        if self.translator_cache is not None:
            for key, translator in self.translator_cache.items():
                if translator:
                    try:
                        translator.close()
                    except Exception as e:
                        print(f"Error closing translator {key}: {e}")
            self.translator_cache.clear()
            self.translator_cache = None

        if not self._agent_running:
            self._flow("audio.shutdown", agent_running=False)
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
        self._flow("audio.shutdown", agent_running=True)


    def set_on_agent_chunk(self, callback: Callable):
        """
        Set callback for streaming agent response chunks.
        Callback signature: callback(message: dict)
        Each message has type="agent_chunk" with a "chunk" field.
        """
        self._on_agent_chunk = callback

    def _run_agent(self, prompt_text: str):
        if not self.ollama_client or not self.agent_enabled or not prompt_text:
            return
        if not self.agent_model:
            return

        # Set flag for barge-in detection
        self._is_agent_generating = True
        self._current_agent_prompt = prompt_text
        self._flow("agent.run_start", model=self.agent_model, prompt_len=len(prompt_text))
        
        try:
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
                self._flow("agent.run_cancelled", phase="before_generation")
                return

            # Notify frontend that agent is starting to respond
            if self._on_agent_chunk:
                self._on_agent_chunk({
                    "type": "agent_chunk",
                    "status": "start",
                    "model": self.agent_model,
                    "chunk": ""
                })

            # Stream callback: send each token to frontend in real-time
            def on_chunk(chunk_text: str):
                if chunk_text:
                    if self._on_agent_chunk:
                        self._on_agent_chunk({
                            "type": "agent_chunk",
                            "status": "streaming",
                            "chunk": chunk_text
                        })

            response = self.ollama_client.generate(
                self.agent_model,
                full_prompt,
                stream=True,
                callback=on_chunk,
                cancel_event=self._agent_cancelled
            )

            # Check if cancelled after generation (barge-in during LLM call)
            if self._agent_cancelled.is_set():
                print(f"[{_ts()}] [AGENT] Cancelled after generation (barge-in)")
                self._flow("agent.run_cancelled", phase="after_generation")
                if self._on_agent_chunk:
                    self._on_agent_chunk({
                        "type": "agent_chunk",
                        "status": "cancelled",
                        "chunk": ""
                    })
                # NOTE: History for interrupted responses is saved by set_barge_in_context()
                # which uses TTS spoken text (what the user actually heard)
                return
            if not response:
                self._flow("agent.run_empty_response", level=logging.WARNING)
                if self._on_agent:
                    self._on_agent({
                        "type": "agent",
                        "status": "error",
                        "model": self.agent_model,
                        "error": "No response from model"
                    })
                return

            # Notify streaming is done
            if self._on_agent_chunk:
                self._on_agent_chunk({
                    "type": "agent_chunk",
                    "status": "done",
                    "chunk": ""
                })

            # Send complete response (triggers TTS)
            if self._on_agent:
                self._on_agent({
                    "type": "agent",
                    "status": "ok",
                    "model": self.agent_model,
                    "prompt": prompt_text,
                    "response": response
                })
            self._flow("agent.run_done", response_len=len(response))
            self._agent_history.append({
                "transcript": prompt_text,
                "response": response,
                "interrupted": False
            })
            if len(self._agent_history) > AGENT_HISTORY_LIMIT:
                self._agent_history = self._agent_history[-AGENT_HISTORY_LIMIT:]
                
        finally:
            self._is_agent_generating = False
            self._current_agent_prompt = None
            self._flow("agent.run_end")


    def _format_agent_prompt(self, current_text: str) -> str:
        system_prompt = [
            "System:",
            "Always respond in a friendly tone.",
            "Keep responses short.",
            "Use only plain text (no markdown).",
            "Respond in the same language as the user input.",
            "If your previous response was interrupted by the user, do not repeat what they already heard. Respond to their new input directly."
        ]
        if not self._agent_history:
            return "\n".join(system_prompt + ["New transcription:", current_text])
        lines = system_prompt + ["Context (latest transcriptions and responses):"]
        for item in self._agent_history[-AGENT_HISTORY_LIMIT:]:
            if item.get("transcript"):
                lines.append(f"Transcription: {item['transcript']}")
            if item.get("interrupted"):
                spoken = item.get("spoken", "")
                full = item.get("response", "")
                if spoken:
                    lines.append(f"Your response (user heard this part): {spoken}")
                    lines.append(f"Your response (user did NOT hear this part): {full[len(spoken):].strip()}")
                else:
                    lines.append(f"Your response (interrupted before user could hear it): {full[:100]}...")
            else:
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
            self._flow("turn.accumulate", parts=len(self._turn_buffer), appended_len=len(text))

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
        self._flow("turn.flush", combined_len=len(combined_text))
        self._enqueue_agent_prompt(combined_text)

    def _handle_final(self, text: str, confidence: float):
        """Internal handler for final transcriptions."""
        
        # Reset live partial buffer when a final result is committed
        self._last_partial_text = ""
        
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
            self._flow(
                "stt.final",
                text_len=len(text),
                confidence=round(confidence, 3),
                translated_len=len(translated_text or ""),
            )

            if self.agent_enabled and self.ollama_client and self._on_agent:
                prompt_text = text or translated_text
                self._accumulate_turn(prompt_text)
                
        except Exception as e:
            print(f"[{_ts()}] Translation error: {e}")
    
    def _handle_partial(self, text: str):
        """Internal handler for partial transcriptions."""
        partial_text = (text or "").strip()
        if not partial_text:
            if self._debug_partials:
                print(f"[{_ts()}] [PARTIAL][SKIP empty]")
            return

        # Ignore duplicate partials
        if partial_text == self._last_partial_text:
            if self._debug_partials:
                print(f"[{_ts()}] [PARTIAL][SKIP duplicate] len={len(partial_text)}")
            return

        # Ignore decoder rollbacks to avoid UI flicker on trailing words
        if self._last_partial_text and self._last_partial_text.startswith(partial_text):
            if self._debug_partials:
                print(
                    f"[{_ts()}] [PARTIAL][SKIP rollback] "
                    f"prev_len={len(self._last_partial_text)} new_len={len(partial_text)} "
                    f"prev='{self._last_partial_text[:40]}' new='{partial_text[:40]}'"
                )
            return

        if self._debug_partials:
            print(
                f"[{_ts()}] [PARTIAL][EMIT] prev_len={len(self._last_partial_text)} "
                f"new_len={len(partial_text)} text='{partial_text[:80]}'"
            )

        self._last_partial_text = partial_text
        if self._flow_log_partials:
            self._flow("stt.partial", level=logging.DEBUG, text_len=len(partial_text))

        # Barge-in: if TTS is speaking OR Agent is generating and user starts talking, interrupt it
        if (self._tts_speaking or self._is_agent_generating):
            self.barge_in()


        message = {
            "type": "partial",
            "original": partial_text
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
