import os
import urllib.request
import zipfile

MODELS_DIR = "./models"

AVAILABLE_MODELS = {
    "1": {
        "name": "vosk-model-en-us-0.22-lgraph",
        "url": "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22-lgraph.zip",
        "lang": "English (ligero)"
    },
    "2": {
        "name": "vosk-model-en-us-0.22",
        "url": "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip",
        "lang": "English (completo)"
    },
    "3": {
        "name": "vosk-model-en-us-0.42-gigaspeech",
        "url": "https://alphacephei.com/vosk/models/vosk-model-en-us-0.42-gigaspeech.zip",
        "lang": "English (completo)"
    },
    "4": {
        "name": "vosk-model-small-es-0.42",
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip",
        "lang": "Español (ligero)"
    },
    "5": {
        "name": "vosk-model-es-0.42",
        "url": "https://alphacephei.com/vosk/models/vosk-model-es-0.42.zip",
        "lang": "Español (completo)"
    },
}


def is_model_downloaded(model_name):
    """Verifica si el modelo está descargado."""
    model_path = os.path.join(MODELS_DIR, model_name)
    return os.path.isdir(model_path)


def download_with_progress(url, dest_path):
    """Descarga archivo mostrando progreso."""
    def report_progress(block_num, block_size, total_size):
        downloaded = block_num * block_size
        percent = min(100, downloaded * 100 / total_size)
        bar_len = 30
        filled = int(bar_len * percent / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r  Descargando: [{bar}] {percent:.1f}%", end="", flush=True)
    
    urllib.request.urlretrieve(url, dest_path, reporthook=report_progress)
    print()


def extract_model(zip_path):
    """Extrae el modelo del zip."""
    print("  Extrayendo...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(MODELS_DIR)
    os.remove(zip_path)
    print("  ✓ Modelo listo")


def download_model(model_info):
    """Descarga y extrae un modelo."""
    os.makedirs(MODELS_DIR, exist_ok=True)
    zip_name = model_info["url"].split("/")[-1]
    zip_path = os.path.join(MODELS_DIR, zip_name)
    
    print(f"\n  Descargando {model_info['name']}...")
    download_with_progress(model_info["url"], zip_path)
    extract_model(zip_path)


def select_vosk_model():
    """Muestra menú para seleccionar modelo Vosk."""
    print("\n=== Modelos Vosk Disponibles ===\n")
    
    for key, model in AVAILABLE_MODELS.items():
        status = "✓" if is_model_downloaded(model["name"]) else "○"
        print(f"  [{key}] {status} {model['lang']} - {model['name']}")
    
    print("\n  ✓ = descargado, ○ = no descargado\n")
    
    while True:
        try:
            choice = input("Selecciona modelo (1-4): ").strip()
            
            if choice not in AVAILABLE_MODELS:
                print("Opción no válida. Elige 1-4.")
                continue
            
            model = AVAILABLE_MODELS[choice]
            model_path = os.path.join(MODELS_DIR, model["name"])
            
            if not is_model_downloaded(model["name"]):
                confirm = input(f"  Modelo no descargado. ¿Descargar? (s/n): ").strip().lower()
                if confirm == 's':
                    download_model(model)
                else:
                    continue
            
            print(f"\n✓ Modelo seleccionado: {model['name']}\n")
            return model_path
            
        except KeyboardInterrupt:
            print("\nCancelado.")
            exit(0)
        except Exception as e:
            print(f"Error: {e}")
