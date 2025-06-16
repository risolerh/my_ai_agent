from transformers import MarianMTModel, MarianTokenizer

class EnglishToSpanishTranslator:
    def __init__(self):
        model_name = 'Helsinki-NLP/opus-mt-en-es'
        self.tokenizer = MarianTokenizer.from_pretrained(model_name)
        self.model = MarianMTModel.from_pretrained(model_name)

    def translate(self, text: str) -> str:
        batch = self.tokenizer([text], return_tensors="pt", padding=True)
        generated_ids = self.model.generate(**batch)
        translated = self.tokenizer.decode(generated_ids[0], skip_special_tokens=True)
        return translated
    
if __name__ == "__main__":
    translator = EnglishToSpanishTranslator()
    english_text = "This is a test. How are you today?"
    spanish_text = translator.translate(english_text)
    print(f"Inglés: {english_text}")
    print(f"Español: {spanish_text}")