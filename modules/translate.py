import threading
from transformers import MarianMTModel, MarianTokenizer
import torch

import queue
import time

class EnglishToSpanishTranslator:
    def __init__(self):
        model_name = 'Helsinki-NLP/opus-mt-en-es'
        self.tokenizer = MarianTokenizer.from_pretrained(model_name)
        self.model = MarianMTModel.from_pretrained(model_name)
        
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







if __name__ == "__main__":
    translator = EnglishToSpanishTranslator()
    print("... Iniciando test de 10 peticiones al debounced...")

    def print_result(result):
        print(f"-----> Traduccion: {result}")

    for i in range(1,10):
        # print(f"#{i} peticion al debounced")
        english_text = f"This is test number {i}"
        translator.translate_debounced(english_text, callback=print_result)
    
    print("! se enviaron 10 peticicness....")
    threading.Event().wait(2)

    for i in range(11,20):
        # print(f"#{i} peticion al debounced")
        english_text = f"This is test number {i}"
        translator.translate_debounced(english_text, callback=print_result)

    print("! se enviaron otras 10 peticicioes....")
    print(f" <--------- {translator.translate('Hello, how are you?')} ")

    # Espera suficiente para que el último debounce termine
    threading.Event().wait(5)