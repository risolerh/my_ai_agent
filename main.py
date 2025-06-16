from modules.translate import EnglishToSpanishTranslator
from modules.audio_listener import AudioListener
from modules.page import Page


def on_translated_enbounced(text_translated):    
    page.update_second_text(text_translated)



def on_partial(text):
    page.update_current_text(text)    
    translator.translate_debounced(text, callback=on_translated_enbounced)    

def on_final(english_text):
    spanish_text = translator.translate(english_text)
    page.add_traduction(english_text, spanish_text)

def on_current(text):
    print(text, end="", flush=True)



# translator service
translator = EnglishToSpanishTranslator()

# Audio listener service
listener = AudioListener(
    block_size=1000,
    model_path="./models/vosk-model-en-us-0.22-lgraph", 
    # model_path="./models/vosk-model-en-us-0.22", 
    device_id=8)
listener.set_on_final(on_final)
listener.set_on_partial(on_partial)
listener.set_on_current(on_current)
listener.listen_in_thread()
print("Escuchando... Ctrl+C para salir")

# Screen service
page = Page()
page.run()
