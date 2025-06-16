import tkinter as tk

WITH_SIZE = 500

class Page:
    def __init__(self, title="Mi Aplicación de Escritorio", size=f"500x{WITH_SIZE}"):
        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry(size)

        self._create_top_section()
        self._create_bottom_section()

# CONTENEDORES DE LA PARTE SUPERIOR
    def _create_top_section(self):
        container = tk.Frame(self.root)
        container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(container)
        self.canvas.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        scrollbar.pack(side="right", fill="y")

        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.top_frame = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.top_frame, anchor="nw")

        self.top_frame.bind("<Configure>", self.on_frame_configure)

    def on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    # CONTENEDORES DE LA PARTE INFERIOR

    def _create_bottom_section(self):
        bottom_frame = tk.Frame(self.root)  # Quita height=100
        bottom_frame.pack(side="bottom", fill="both", expand=False, pady=10)
        # No uses pack_propagate(False)

        self._create_first_container(bottom_frame)
        self._create_second_container(bottom_frame)

    def _create_first_container(self, parent):
        left_frame = tk.Frame(parent)
        left_frame.pack(side="top", fill="both", expand=True, padx=(0, 5))

        bottom_scrollbar = tk.Scrollbar(left_frame)
        bottom_scrollbar.pack(side="right", fill="y")

        self.english_current_text = tk.Text(
            left_frame,
            wrap="word",
            yscrollcommand=bottom_scrollbar.set,
            height=5  # Puedes ajustar la altura
        )
        self.english_current_text.pack(side="left", fill="both", expand=True)
        bottom_scrollbar.config(command=self.english_current_text.yview)
        self.english_current_text.config(state="disabled")

    def _create_second_container(self, parent):
        right_frame = tk.Frame(parent)
        right_frame.pack(side="top", fill="both", expand=True, padx=(0, 5))

        bottom_scrollbar = tk.Scrollbar(right_frame)
        bottom_scrollbar.pack(side="right", fill="y")

        self.second_text = tk.Text(
            right_frame,
            wrap="word",
            yscrollcommand=bottom_scrollbar.set,
            height=5  # Puedes ajustar la altura
        )
        self.second_text.pack(side="left", fill="both", expand=True)
        self.second_text.config(state="disabled")


    
    def add_traduction(self, eng, esp):
        tk.Label(
            self.top_frame,
            text=eng,
            fg="black",
            anchor="w",
            justify="left",
            wraplength=(WITH_SIZE-20)  # Ajusta el ancho de wrap aquí
        ).pack(fill="x", anchor="w")
        tk.Label(
            self.top_frame,
            text=esp,
            fg="blue",
            anchor="w",
            padx=0,
            justify="left",
            wraplength=(WITH_SIZE-20)  # Ajusta el ancho de wrap aquí
        ).pack(fill="x", anchor="w")

    
    def update_current_text(self, text):
        self.english_current_text.config(state="normal")
        self.english_current_text.delete("1.0", tk.END)
        self.english_current_text.insert(tk.END, text)
        self.english_current_text.config(state="disabled")


    def update_second_text(self, text):
        self.second_text.config(state="normal")
        self.second_text.delete("1.0", tk.END)
        self.second_text.insert(tk.END, text)
        self.second_text.config(state="disabled")


    def run(self):
        self.root.mainloop()

# Ejemplo de uso:
if __name__ == "__main__":
    page = Page()
    page.add_traduction("Hello, world!", "Hola, mundo!")
    page.add_traduction("Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book. It has survived not only five centuries, but also the leap into electronic typesetting, remaining essentially unchanged. I", "Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book. It has survived not only five centuries, but also the leap into electronic typesetting, remaining essentially unchanged. I")
    page.update_current_text("Texto prueba")
    page.update_second_text("Texto independiente")
    page.run()