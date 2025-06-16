import sounddevice as sd
import queue
import vosk
import sys
import json

# Configuración
SAMPLE_RATE = 32000   
BLOCK_SIZE = 4000  # Tamaño del bloque de audio
CHANNELS = 1  # Mono
DTYPE = 'int16'  # Tipo de dato del audio
ID_DEVICE = 8  # Voicemeeter Out B1 (VB-Audio Voicemeeter VAIO), MME (8 in, 0 out)


# Cargar modelo Vosk
model = vosk.Model("./models/vosk-model-en-us-0.22")
q = queue.Queue()



# Callback para capturar audio // Mezcla estéreo
def callback(indata, frames, time, status):
    q.put(bytes(indata))



with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize = BLOCK_SIZE, device=ID_DEVICE,
        dtype=DTYPE, channels=CHANNELS, callback=callback):
    rec = vosk.KaldiRecognizer(model, SAMPLE_RATE)
    print("Escuchando... Ctrl+C para salir")
    last_partial = ""
    text_validated = []
    try:
        while True:
            data = q.get()
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result()).get("text", "")
                if result:
                    print("\n\n<--- ", result, " -->\n")
                    text_validated.append(result)
                    last_partial = ""  # Reinicia el parcial después de un resultado final
            else:
                partial = rec.PartialResult()
                # Extrae solo el texto del resultado parcial
                partial_text = json.loads(partial).get("partial", "")
                if partial_text and partial_text != last_partial:
                    # Imprime solo lo nuevo
                    print(partial_text[len(last_partial):], end=" ", flush=True)
                    last_partial = partial_text
    except KeyboardInterrupt:
        print("\nFinalizado por el usuario.")






