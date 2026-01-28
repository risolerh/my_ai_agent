import tkinter as tk
from tkinter import ttk
import sounddevice as sd
import os

WIDTH_SIZE = 600
from modules.model_selector import AVAILABLE_MODELS, MODELS_DIR


class Page:
    def __init__(self, title="Traductor en Tiempo Real", size=f"{WIDTH_SIZE}x600"):
        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry(size)
        
        self._on_config_change = None
        self._on_close = None
        
        # Config params
        self.latency_var = tk.DoubleVar(value=0.05)  # Default 50ms
        
        # Manejar cierre de ventana
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self._create_config_section()
        
        # Main PanedWindow to split History (Top) and Inputs (Bottom)
        self.main_paned = tk.PanedWindow(self.root, orient=tk.VERTICAL, sashwidth=5, bg="gray60", sashrelief=tk.RAISED)
        self.main_paned.pack(fill="both", expand=True, padx=10, pady=10)
        
        self._create_top_section()
        self._create_bottom_section()

    def set_on_config_change(self, callback):
        """Callback cuando cambia la configuración (model_path, device_id)."""
        self._on_config_change = callback
    
    def set_on_close(self, callback):
        """Callback para limpieza antes de cerrar."""
        self._on_close = callback
    
    def on_closing(self):
        """Maneja el cierre limpio de la aplicación."""
        if self._on_close:
            self._on_close()
        self.root.quit()
        self.root.destroy()

    def _create_config_section(self):
        """Panel de configuración con dropdowns."""
        config_frame = tk.LabelFrame(self.root, text="⚙️ Configuración", padx=10, pady=5)
        config_frame.pack(fill="x", padx=10, pady=(10, 0))
        
        # Frame para modelo
        model_frame = tk.Frame(config_frame)
        model_frame.pack(fill="x", pady=2)
        
        tk.Label(model_frame, text="Modelo:").pack(side="left")
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(model_frame, textvariable=self.model_var, state="readonly", width=35)
        self.model_combo.pack(side="left", padx=(5, 10))
        self._update_model_list()
        self.model_combo.bind("<<ComboboxSelected>>", self._on_config_changed)
        
        # Frame para dispositivo
        device_frame = tk.Frame(config_frame)
        device_frame.pack(fill="x", pady=2)
        
        tk.Label(device_frame, text="Audio:").pack(side="left")
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(device_frame, textvariable=self.device_var, state="readonly", width=40)
        self.device_combo.pack(side="left", padx=(5, 10))
        self._update_device_list()
        self.device_combo.bind("<<ComboboxSelected>>", self._on_config_changed)
        
        # Botones extra
        btn_frame = tk.Frame(device_frame)
        btn_frame.pack(side="left", padx=5)

        # Botón refrescar
        refresh_btn = tk.Button(btn_frame, text="🔄", command=self._refresh_devices)
        refresh_btn.pack(side="left", padx=2)

        # Botón ajustes avanzados
        settings_btn = tk.Button(btn_frame, text="⚙️", command=self._open_settings)
        settings_btn.pack(side="left", padx=2)
        
        # Audio level meter
        level_frame = tk.Frame(config_frame)
        level_frame.pack(fill="x", pady=2)
        tk.Label(level_frame, text="Nivel:").pack(side="left")
        
        self.audio_level_canvas = tk.Canvas(level_frame, height=20, bg="gray20")
        self.audio_level_canvas.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.audio_level_bar = self.audio_level_canvas.create_rectangle(
            0, 0, 0, 20, fill="green", outline=""
        )
        
        # Estado
        self.status_label = tk.Label(config_frame, text="⏸️ Configurando...", fg="gray")
        self.status_label.pack(anchor="w", pady=(5, 0))

    def _update_model_list(self):
        """Actualiza lista de modelos disponibles."""
        models = []
        for info in AVAILABLE_MODELS.values():
            model_name = info["name"]
            display_name = info["lang"]
            model_path = os.path.join(MODELS_DIR, model_name)
            if os.path.isdir(model_path):
                models.append(f"✓ {display_name} ({model_name})")
            else:
                models.append(f"○ {display_name} ({model_name})")
        
        self.model_combo['values'] = models
        # Seleccionar primer modelo descargado
        for i, m in enumerate(models):
            if m.startswith("✓"):
                self.model_combo.current(i)
                break

    def _update_device_list(self):
        """Actualiza lista de dispositivos de audio."""
        devices = sd.query_devices()
        self.device_list = []
        device_names = []
        
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                name = f"[{i}] {dev['name']}"
                device_names.append(name)
                self.device_list.append((i, dev['name']))
        
        self.device_combo['values'] = device_names
        # Seleccionar 'default' o 'pulse' si existe
        for i, (dev_id, name) in enumerate(self.device_list):
            if 'pulse' in name.lower() or 'default' in name.lower():
                self.device_combo.current(i)
                break
        else:
            if self.device_list:
                self.device_combo.current(0)

    def _refresh_devices(self):
        """Refresca la lista de dispositivos."""
        self._update_device_list()

    def _on_config_changed(self, event=None):
        """Cuando cambia la selección de modelo o dispositivo."""
        if self._on_config_change:
            model_path = self.get_selected_model_path()
            device_id = self.get_selected_device_id()
            latency = self.get_selected_latency()
            if model_path and device_id is not None:
                self._on_config_change(model_path, device_id, latency)

    def get_selected_model_path(self):
        """Obtiene la ruta del modelo seleccionado."""
        selection = self.model_var.get()
        if not selection:
            return None
        # Extraer nombre del modelo entre paréntesis
        if "(" in selection and ")" in selection:
            model_name = selection.split("(")[-1].rstrip(")")
            return os.path.join(MODELS_DIR, model_name)
        return None

    def get_selected_device_id(self):
        """Obtiene el ID del dispositivo seleccionado."""
        idx = self.device_combo.current()
        if idx >= 0 and idx < len(self.device_list):
            return self.device_list[idx][0]
        return None

    def get_selected_latency(self):
        return self.latency_var.get()

    def _open_settings(self):
        """Abre ventana de configuración avanzada."""
        win = tk.Toplevel(self.root)
        win.title("Ajustes Avanzados de Vosk")
        win.geometry("350x200")
        win.transient(self.root)
        
        tk.Label(win, text="Configuración de Latencia y Buffer", font=("Arial", 11, "bold")).pack(pady=(15, 5))
        tk.Label(win, text="Controla qué tan rápido responde el modelo.\nMenor latencia = respuestas más rápidas pero más uso de CPU.", 
                 font=("Arial", 9), justify="center").pack(pady=5)

        # Scale for latency: 0.02s to 0.5s
        frame = tk.Frame(win)
        frame.pack(pady=10)
        
        tk.Label(frame, text="Buffer (segundos):").pack(side="left")
        scale = tk.Scale(
            frame, 
            from_=0.02, 
            to=0.5, 
            resolution=0.01, 
            orient=tk.HORIZONTAL, 
            variable=self.latency_var,
            length=150
        )
        scale.pack(side="left", padx=5)

        def apply():
            self._on_config_changed()
            win.destroy()

        tk.Button(win, text="Aplicar y Reiniciar Listener", command=apply, bg="#e1e1e1", padx=10, pady=5).pack(pady=10)

    def set_status(self, text, color="green"):
        """Actualiza el estado."""
        self.status_label.config(text=text, fg=color)
    
    def update_audio_level(self, level):
        """Actualiza la barra de nivel de audio (0.0-1.0) - thread-safe."""
        def update():
            try:
                width = self.audio_level_canvas.winfo_width()
                bar_width = int(width * min(level * 3, 1.0))  # Amplificar x3 para mejor visualización
                
                # Color según nivel
                if level > 0.3:
                    color = "green"
                elif level > 0.1:
                    color = "yellow"
                else:
                    color = "gray40"
                
                self.audio_level_canvas.coords(self.audio_level_bar, 0, 0, bar_width, 20)
                self.audio_level_canvas.itemconfig(self.audio_level_bar, fill=color)
            except:
                pass  # Ignorar si la ventana está cerrada
        
        # Ejecutar en el thread principal
        self.root.after(0, update)

    def _create_top_section(self):
        container = tk.Frame(self.main_paned)
        self.main_paned.add(container, minsize=100, stretch="always")

        # Etiqueta de sección
        tk.Label(container, text="📜 Texto Final", font=("Arial", 10, "bold"), anchor="w").pack(fill="x", padx=5, pady=(5,0))

        # Usar Text widget en lugar de Canvas para permitir copiar texto
        self.history_text = tk.Text(container, wrap="word", padx=10, pady=10, bg="#f0f0f0")
        scrollbar = tk.Scrollbar(container, orient="vertical", command=self.history_text.yview)
        
        self.history_text.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side="right", fill="y")
        self.history_text.pack(side="left", fill="both", expand=True)
        
        self.history_text.config(state="disabled")

        # Configurar tags para estilos (colores)
        self.history_text.tag_config("eng", foreground="black", font=("Arial", 10))
        self.history_text.tag_config("esp", foreground="blue", font=("Arial", 10, "italic"))
        self.history_text.tag_config("sep", foreground="gray", font=("Arial", 6))

    def on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _create_bottom_section(self):
        """Crea sección inferior con cuadros redimensionables."""
        # PanedWindow vertical interior
        inner_paned = tk.PanedWindow(self.main_paned, orient=tk.VERTICAL, sashwidth=5, bg="gray60", sashrelief=tk.RAISED)
        self.main_paned.add(inner_paned, minsize=150, stretch="always")
        
        # Frame para texto original
        left_frame = tk.LabelFrame(inner_paned, text="🎤 Flujo Realtime")
        inner_paned.add(left_frame, minsize=60, stretch="always")
        
        bottom_scrollbar = tk.Scrollbar(left_frame)
        bottom_scrollbar.pack(side="right", fill="y")
        
        self.english_current_text = tk.Text(
            left_frame, wrap="word", yscrollcommand=bottom_scrollbar.set, height=4
        )
        self.english_current_text.pack(side="left", fill="both", expand=True)
        bottom_scrollbar.config(command=self.english_current_text.yview)
        self.english_current_text.config(state="disabled")
        
        # Frame para traducción
        right_frame = tk.LabelFrame(inner_paned, text="🌐 Traducción")
        inner_paned.add(right_frame, minsize=60, stretch="always")
        
        bottom_scrollbar2 = tk.Scrollbar(right_frame)
        bottom_scrollbar2.pack(side="right", fill="y")
        
        self.second_text = tk.Text(
            right_frame, wrap="word", yscrollcommand=bottom_scrollbar2.set, height=4
        )
        self.second_text.pack(side="left", fill="both", expand=True)
        self.second_text.config(state="disabled")

    def add_traduction(self, eng, esp, confidence=None):
        self.history_text.config(state="normal")
        
        # Texto inglés con indicador de confianza
        eng_text = eng
        if confidence is not None:
            conf_percent = int(confidence * 100)
            # Solo mostrar porcentaje si es real (mayor a 0)
            if conf_percent > 0:
                eng_text = f"{eng} [{conf_percent}%]"
        
        # Insertar en el Text widget
        self.history_text.insert(tk.END, f"{eng_text}\n", "eng")
        self.history_text.insert(tk.END, f"{esp}\n", "esp")
        self.history_text.insert(tk.END, f"{'-'*40}\n", "sep")
        
        self.history_text.see(tk.END)  # Auto-scroll
        self.history_text.config(state="disabled")

    def update_current_text(self, text):
        self.english_current_text.config(state="normal")
        self.english_current_text.delete("1.0", tk.END)
        self.english_current_text.insert(tk.END, text)
        self.english_current_text.config(state="disabled")

    def clear_current_text(self):
        """Limpia el cuadro de texto original (realtime)."""
        self.english_current_text.config(state="normal")
        self.english_current_text.delete("1.0", tk.END)
        self.english_current_text.config(state="disabled")

    def update_second_text(self, text):
        self.second_text.config(state="normal")
        self.second_text.delete("1.0", tk.END)
        self.second_text.insert(tk.END, text)
        self.second_text.config(state="disabled")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    page = Page()
    page.run()