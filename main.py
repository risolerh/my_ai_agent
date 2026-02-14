import os
import signal
import traceback
from pathlib import Path
from typing import Optional

from modules.audio_listener import AudioListener
from modules.logger import TranscriptionLogger
from modules.model_selector import AVAILABLE_MODELS
from modules.translate import EnglishToSpanishTranslator
from view.page import Page

TARGET_LANG = os.getenv("DESKTOP_TARGET_LANG", "es")

translator: Optional[EnglishToSpanishTranslator] = None
listener: Optional[AudioListener] = None
page: Optional[Page] = None
logger: Optional[TranscriptionLogger] = None
_closing = False


def _resolve_source_lang(model_path: str) -> str:
    model_name = Path(model_path).name
    for info in AVAILABLE_MODELS.values():
        if info["name"] == model_name:
            return info.get("code", "en")
    return "en"


def _reset_translator(source_lang: str):
    global translator

    if translator:
        translator.close()

    translator = EnglishToSpanishTranslator(source_lang=source_lang, target_lang=TARGET_LANG)
    translator.start_worker(
        on_text_ready=page.update_current_text,
        on_translation_ready=page.update_second_text,
    )


def on_final(text: str, confidence: float):
    translated = text
    if translator:
        translated = translator.translate(text)

    page.add_traduction(text, translated, confidence)

    if logger:
        logger.log(text, translated)

    page.clear_current_text()
    print(f"[{confidence:.2f}] {text}")


def on_partial(text: str):
    if translator:
        translator.enqueue(text)


def on_current(text: str):
    _ = text


def on_audio_level(level: float):
    if page and not page.is_closing:
        page.update_audio_level(level)


def start_listener(model_path: str, device_id: int, latency: float = 0.05):
    global listener

    page.set_status("⏳ Conectando a servicios gRPC...", "orange")
    page.root.update()

    if listener:
        listener.stop()

    try:
        source_lang = _resolve_source_lang(model_path)
        _reset_translator(source_lang)

        listener = AudioListener(
            model_path=model_path,
            device_id=device_id,
            latency=latency,
        )
        listener.set_on_final(on_final)
        listener.set_on_partial(on_partial)
        listener.set_on_current(on_current)
        listener.set_on_audio_level(on_audio_level)
        listener.listen_in_thread()

        page.set_status(f"🎙️ Escuchando por gRPC... (Latencia: {latency:.2f}s)", "green")
        print(f"Escuchando... model={model_path} device={device_id} latency={latency}")
    except Exception as e:
        page.set_status(f"❌ Error: {str(e)[:60]}", "red")
        print(f"Error iniciando listener: {e}")


def on_config_change(model_path: str, device_id: int, latency: float):
    start_listener(model_path, device_id, latency)


def on_app_close():
    global listener, translator, _closing

    if _closing:
        return
    _closing = True

    # During shutdown, ignore extra Ctrl+C to avoid noisy atexit traces.
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except Exception:
        pass

    if listener:
        try:
            listener.stop()
        except Exception:
            print("Error cerrando listener:")
            traceback.print_exc()
        finally:
            listener = None

    if translator:
        try:
            translator.close()
        except Exception:
            print("Error cerrando traductor:")
            traceback.print_exc()
        finally:
            translator = None


def main():
    global page, logger, _closing

    print("Iniciando app de escritorio (gRPC)...")

    logger = TranscriptionLogger()

    page = Page(title="Traductor Desktop (gRPC)")
    page.set_on_config_change(on_config_change)
    page.set_on_close(on_app_close)

    model_path = page.get_selected_model_path()
    device_id = page.get_selected_device_id()
    latency = page.get_selected_latency()

    if model_path and device_id is not None:
        start_listener(model_path, device_id, latency)
    else:
        page.set_status("⚠️ Selecciona modelo y dispositivo", "orange")

    try:
        page.run()
    except KeyboardInterrupt:
        print("\nInterrupción detectada. Cerrando sesión de escritorio...")
    except Exception:
        print("\nError inesperado en app de escritorio:")
        traceback.print_exc()
    finally:
        on_app_close()


if __name__ == "__main__":
    main()
