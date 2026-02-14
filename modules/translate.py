import queue
import threading
from typing import Callable, Optional

from modules.grpc_translator import GrpcTranslator


class Translator:
    """Compatibility wrapper that delegates translation to gRPC service."""

    def __init__(self, source_lang: str = "en", target_lang: str = "es"):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.client = GrpcTranslator(source_lang=source_lang, target_lang=target_lang)

        self.queue: queue.Queue[str] = queue.Queue()
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def translate(self, text: str) -> str:
        if not text:
            return ""
        if self.source_lang == self.target_lang:
            return text
        return self.client.translate(text)

    def start_worker(self, on_text_ready: Optional[Callable], on_translation_ready: Optional[Callable]):
        self.running = True
        self.thread = threading.Thread(
            target=self._worker_loop,
            args=(on_text_ready, on_translation_ready),
            daemon=True,
        )
        self.thread.start()

    def stop_worker(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def enqueue(self, text: str):
        if self.running and text:
            self.queue.put(text)

    def _worker_loop(self, on_text_ready: Optional[Callable], on_translation_ready: Optional[Callable]):
        while self.running:
            try:
                text = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue

            while not self.queue.empty():
                try:
                    text = self.queue.get_nowait()
                except queue.Empty:
                    break

            if not text:
                continue

            if on_text_ready:
                on_text_ready(text)

            translated = self.translate(text)
            if on_translation_ready:
                on_translation_ready(translated)

    def close(self):
        self.stop_worker()
        self.client.close()


class EnglishToSpanishTranslator(Translator):
    def __init__(self, source_lang: str = "en", target_lang: str = "es"):
        super().__init__(source_lang=source_lang, target_lang=target_lang)
