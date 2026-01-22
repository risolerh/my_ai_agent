from modules.translate import EnglishToSpanishTranslator
from modules.audio_listener import AudioListener
from modules.page import Page
from modules.logger import TranscriptionLogger


# Variables globales
translator = None
listener = None
page = None
logger = None


def on_final(english_text, confidence):
    """Recibe texto y confianza de transcripción."""
    # Traducir el final siempre, con prioridad
    spanish_text = translator.translate(english_text)
    page.add_traduction(english_text, spanish_text, confidence)
    
    # Guardar en archivo
    if logger:
        logger.log(english_text, spanish_text)
    
    # Limpiar el texto realtime ya que se confirmó
    page.clear_current_text()
    
    print(f"\n[{confidence:.2f}] {english_text}")


def on_current(text):
    print(text, end="", flush=True)


def on_partial(text):
    # Encolar para traducción en background
    if translator:
        translator.enqueue(text)


def on_audio_level(level):
    """Actualiza el nivel de audio en la UI."""
    page.update_audio_level(level)


def start_listener(model_path, device_id, latency=0.05):
    """Inicia o reinicia el listener con nueva configuración."""
    global listener
    
    # Mostrar indicador de carga
    page.set_status("⏳ Cargando modelo...", "orange")
    page.root.update()  # Forzar actualización de UI
    
    # Detener listener anterior si existe
    if listener:
        listener.stop()
    
    try:
        listener = AudioListener(
            model_path=model_path,
            device_id=device_id,
            latency=latency
        )
        listener.set_on_final(on_final)
        listener.set_on_partial(on_partial)
        listener.set_on_current(on_current)
        listener.set_on_audio_level(on_audio_level)
        listener.listen_in_thread()
        page.set_status(f"🎙️ Escuchando... (Latencia: {latency:.2f}s)", "green")
        print(f"\nEscuchando... (modelo: {model_path}, dispositivo: {device_id}, latencia: {latency})")
        print(f"Sample rate: {listener.sample_rate} Hz, Block size: {listener.block_size}")
    except Exception as e:
        page.set_status(f"❌ Error: {str(e)[:50]}", "red")
        print(f"Error iniciando listener: {e}")


def on_config_change(model_path, device_id, latency):
    """Callback cuando cambia la configuración en la UI."""
    print(f"\n>> Cambiando a modelo: {model_path}, dispositivo: {device_id}, latencia: {latency}")
    start_listener(model_path, device_id, latency)


def on_app_close():
    """Limpieza al cerrar la aplicación."""
    global listener
    print("\nCerrando aplicación...")
    if listener:
        listener.stop()
    if translator:
        translator.stop_worker()


# Inicializar
print("Iniciando Traductor en Tiempo Real...")

# Logger service
logger = TranscriptionLogger()

# Translator service
translator = EnglishToSpanishTranslator()

# Screen service
page = Page()
page.set_on_config_change(on_config_change)
page.set_on_close(on_app_close)

# Iniciar worker de traducción (Background)
# Callbacks para actualizar la UI: (texto_original, texto_traducido)
translator.start_worker(
    on_text_ready=page.update_current_text,
    on_translation_ready=page.update_second_text
)

# Iniciar con configuración seleccionada en la UI
model_path = page.get_selected_model_path()
device_id = page.get_selected_device_id()
latency = page.get_selected_latency()

if model_path and device_id is not None:
    start_listener(model_path, device_id, latency)
else:
    page.set_status("⚠️ Selecciona modelo y dispositivo", "orange")

page.run()

