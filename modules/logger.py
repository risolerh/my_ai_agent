import os
import datetime

class TranscriptionLogger:
    def __init__(self, output_dir="output"):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        # Generar nombre de archivo único: output/transcripcion_YYYY-MM-DD_HH-MM-SS.txt
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.output_file = os.path.join(self.output_dir, f"transcripcion_{timestamp}.txt")
        print(f"Guardando transcripción en: {self.output_file}")

    def log(self, eng, esp):
        """Guarda la transcripción en el archivo de texto."""
        try:
            with open(self.output_file, "a", encoding="utf-8") as f:
                f.write(f"EN: {eng}\n")
                f.write(f"ES: {esp}\n")
                f.write("-" * 20 + "\n")
        except Exception as e:
            print(f"Error escribiendo en archivo: {e}")
