import threading
import os
from pathlib import Path

# Configurar caché local si existe la carpeta models_translate en la raíz del proyecto
# Esto asegura que se usen los modelos locales tanto en Docker como en local
project_root = Path(__file__).parent.parent
local_models_path = project_root / "models_translate"

if local_models_path.exists():
    print(f"Using local transformers cache: {local_models_path.resolve()}")
    os.environ["HF_HOME"] = str(local_models_path.resolve())

from transformers import MarianMTModel, MarianTokenizer
import torch

import queue
import time

class Translator:
    def __init__(self, source_lang: str = "en", target_lang: str = "es"):
        # Map common language codes to Helsinki-NLP models
        # Format: Helsinki-NLP/opus-mt-{src}-{tgt}
        self.model_name = f'Helsinki-NLP/opus-mt-{source_lang}-{target_lang}'
        
        print(f"Loading translation model: {self.model_name}")
        self.tokenizer = MarianTokenizer.from_pretrained(self.model_name)
        self.model = MarianMTModel.from_pretrained(self.model_name)
        
        # Setup device (GPU/CPU)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Translator running on device: {self.device}")
        self.model.to(self.device)
        
        # Worker threading
        self.queue = queue.Queue()
        self.running = False
        self.thread = None

    def translate(self, text: str) -> str:
        batch = self.tokenizer([text], return_tensors="pt", padding=True).to(self.device)
        generated_ids = self.model.generate(
            **batch,
            num_beams=5,
            max_length=128,
            early_stopping=True
        )
        translated = self.tokenizer.decode(generated_ids[0], skip_special_tokens=True)
        return translated

    def start_worker(self, on_text_ready, on_translation_ready):
        """
        Inicia el worker en segundo plano.
        on_text_ready: callback(text) - Se llama antes de traducir (para actualizar UI rápido)
        on_translation_ready: callback(translated_text) - Se llama al terminar traducción
        """
        self.running = True
        self.thread = threading.Thread(
            target=self._worker_loop, 
            args=(on_text_ready, on_translation_ready), 
            daemon=True
        )
        self.thread.start()

    def stop_worker(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def enqueue(self, text):
        """Encola un texto parcial para ser procesado por el worker."""
        if self.running:
            self.queue.put(text)

    def _worker_loop(self, on_text_ready, on_translation_ready):
        while self.running:
            try:
                # Esperar por texto (timeout para permitir checkear self.running)
                text = self.queue.get(timeout=0.5)
                
                # Debounce: Vaciar la cola para quedarse solo con el más reciente
                while not self.queue.empty():
                    try:
                        text = self.queue.get_nowait()
                    except queue.Empty:
                        break
                
                if text:
                    # 1. Notificar que vamos a procesar este texto (UI update instantáneo)
                    if on_text_ready:
                        on_text_ready(text)
                    
                    # 2. Traducir (Bloqueante pero en su propio hilo)
                    translated = self.translate(text)
                    
                    # 3. Notificar resultado
                    if on_translation_ready:
                        on_translation_ready(translated)
                        
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error en worker de traducción: {e}")

# Class alias for backward compatibility
class EnglishToSpanishTranslator(Translator):
    def __init__(self, source_lang: str = "en", target_lang: str = "es"):
        super().__init__(source_lang=source_lang, target_lang=target_lang)

if __name__ == "__main__":
    translator = Translator("en", "es")
    print(f" <--------- {translator.translate('Hello, how are you?')} ")