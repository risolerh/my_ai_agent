import threading
from transformers import MarianMTModel, MarianTokenizer

def debounced(wait_seconds):
    def decorator(fn):
        timer = None
        lock = threading.Lock()
        last_args = {}
        last_callback = [None]

        def wrapper(*args, callback=None, **kwargs):
            nonlocal timer
            with lock:
                last_args.clear()
                last_args['args'] = args
                last_args['kwargs'] = kwargs
                last_callback[0] = callback

                def call_it():
                    result = fn(*last_args['args'], **last_args['kwargs'])
                    if last_callback[0]:
                        last_callback[0](result)

                if timer and timer.is_alive():
                    timer.cancel()
                timer = threading.Timer(wait_seconds, call_it)
                timer.start()
        return wrapper
    return decorator






class EnglishToSpanishTranslator:
    def __init__(self):
        model_name = 'Helsinki-NLP/opus-mt-en-es'
        self.tokenizer = MarianTokenizer.from_pretrained(model_name)
        self.model = MarianMTModel.from_pretrained(model_name)

    @debounced(0.2)
    def translate_debounced(self, text: str) -> str:
        batch = self.tokenizer([text], return_tensors="pt", padding=True)
        generated_ids = self.model.generate(**batch)
        translated = self.tokenizer.decode(generated_ids[0], skip_special_tokens=True)
        return translated

    def translate(self, text: str) -> str:
        batch = self.tokenizer([text], return_tensors="pt", padding=True)
        generated_ids = self.model.generate(**batch)
        translated = self.tokenizer.decode(generated_ids[0], skip_special_tokens=True)
        return translated







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