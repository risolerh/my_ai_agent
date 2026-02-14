import grpc
import os
import sys
import queue
import threading

# Ensure imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "protos"))

from protos import stt_pb2
from protos import stt_pb2_grpc
from modules.stt.base import STTStrategy, STTResult

class GrpcSttStrategy(STTStrategy):
    """
    STT Strategy that connects to a remote gRPC STT service.
    Acts as a client for the bidirectional streaming RPC.
    """
    def __init__(self, 
                 host="127.0.0.1", 
                 port=5002, 
                 strategy="vosk", 
                 model_path=None, 
                 language=None):
        super().__init__()
        # Allow override via env var
        host = os.getenv("STT_SERVICE_HOST", host)
        port = os.getenv("STT_SERVICE_PORT", str(port))
        
        self.target = f"{host}:{port}"
        self.strategy_name = strategy
        self.model_path = model_path
        self.language = language
        
        self.channel = None
        self.stub = None
        
        self._audio_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._send_thread = None
        self._recv_thread = None
        self._sample_rate = 16000
        self._is_running = False
        self._last_partial = ""
        self._debug_partials = os.getenv("STT_DEBUG_PARTIALS", "").lower() in {"1", "true", "yes", "on"}

    def initialize(self, model_path: str = None, sample_rate: int = 16000) -> None:
        """
        Connects to the gRPC service and starts the streaming loops.
        """
        # Note: In the local strategy, initialize loads the model. 
        # Here we just prepare the connection config.
        # The actual RPC starts when we process the first audio chunk? 
        # Or should we start it immediately to be ready?
        # Let's start immediately to catch connection errors early.
        self._sample_rate = sample_rate
        # If model_path passed here, override constructor
        if model_path:
            self.model_path = model_path
            
        print(f"[GrpcStt] Connecting to {self.target} (Strategy: {self.strategy_name})...")
        self.channel = grpc.insecure_channel(self.target)
        self.stub = stt_pb2_grpc.SttServiceStub(self.channel)
        
        self._start_stream()

    def _start_stream(self):
        if self._is_running:
            return
            
        self._is_running = True
        self._stop_event.clear()
        
        # Generator for the request stream
        def request_generator():
            # 1. Send Config
            config = stt_pb2.StreamingConfig(
                strategy=self.strategy_name,
                model_path=self.model_path or "", # Optional
                sample_rate=self._sample_rate,
                language=self.language or ""
            )
            yield stt_pb2.RecognizeRequest(config=config)
            
            # 2. Send Audio
            while not self._stop_event.is_set():
                try:
                    chunk = self._audio_queue.get(timeout=0.5)
                    if chunk is None:
                        # Sentinel to stop
                        return
                    yield stt_pb2.RecognizeRequest(audio_content=chunk)
                except queue.Empty:
                    continue
        
        # Start the bidirectional stream in a background thread to handle responses
        self._recv_thread = threading.Thread(target=self._receive_loop, args=(request_generator(),), daemon=True)
        self._recv_thread.start()

    def _receive_loop(self, request_iterator):
        try:
            # This call blocks until the stream ends or error
            response_iterator = self.stub.StreamingRecognize(request_iterator)
            
            for response in response_iterator:
                # Handle response
                if response.type == "final" and response.is_final:
                    if self._debug_partials:
                        print(f"[GrpcStt][FINAL] len={len(response.text)} text='{response.text[:80]}'")
                    # New sentence committed; reset partial tracking
                    self._last_partial = ""
                    self._emit_final(response.text, response.confidence)
                elif response.type == "partial":
                    partial = (response.text or "").strip()
                    if not partial:
                        continue

                    # Avoid UI flicker: ignore duplicates and simple rollbacks from decoder.
                    if partial == self._last_partial:
                        if self._debug_partials:
                            print(f"[GrpcStt][PARTIAL][SKIP duplicate] len={len(partial)}")
                        continue
                    if self._last_partial and self._last_partial.startswith(partial):
                        if self._debug_partials:
                            print(
                                f"[GrpcStt][PARTIAL][SKIP rollback] "
                                f"prev_len={len(self._last_partial)} new_len={len(partial)} "
                                f"prev='{self._last_partial[:40]}' new='{partial[:40]}'"
                            )
                        continue

                    if self._debug_partials:
                        print(
                            f"[GrpcStt][PARTIAL][EMIT] prev_len={len(self._last_partial)} "
                            f"new_len={len(partial)} text='{partial[:80]}'"
                        )

                    self._last_partial = partial
                    self._emit_partial(partial)
                # elif response.type == "current":
                #    self._emit_current(response.text)

        except grpc.RpcError as e:
            if not self._stop_event.is_set():
                print(f"[GrpcStt] RPC Error: {e}")
        except Exception as e:
            print(f"[GrpcStt] Error in receive loop: {e}")
        finally:
            self._is_running = False

    def process(self, audio_data: bytes) -> None:
        """
        Enqueues audio to be sent to the server.
        Note: The base STTStrategy.process usually returns a result if available immediately.
        Our Grpc implementation is async via callbacks, so we return None here.
        """
        if not self._is_running:
             # Try to restart? Or raise error?
             # For now, simplistic:
             # print("Warning: GrpcStt not running, dropping audio")
             return None

        self._audio_queue.put(audio_data)
        return None

    def reset(self) -> None:
        """
        Resets the stream. 
        For gRPC, this might mean closing the current stream and starting a new one,
        or just sending a reset signal if supported.
        Simplest is to restart the stream.
        """
        self._stop_stream()
        # Drain queue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break
        self._start_stream()

    def _stop_stream(self):
        self._stop_event.set()
        # Unblock generator
        self._audio_queue.put(None)
        if self._recv_thread:
            # We can't join easily because receive_loop is blocked on stub.StreamingRecognize
            # cancelling the channel/stream from another thread might be needed.
            if self.channel:
                 # This might be too aggressive if we want to reuse channel
                 # self.channel.close() 
                 pass
        self._is_running = False

    def get_name(self) -> str:
        return f"gRPC-{self.strategy_name}"

    def is_streaming(self) -> bool:
        return True # It acts as a streaming strategy from the outside

    def close(self):
        self._stop_stream()
        if self.channel:
            self.channel.close()
