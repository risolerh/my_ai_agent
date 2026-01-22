import sounddevice as sd
import sys
import termios
import tty


def get_key():
    """Lee una tecla del teclado."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == '\x1b':  # Escape sequence
            ch += sys.stdin.read(2)
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def select_audio_device():
    """Selector interactivo de dispositivo de audio con teclas arriba/abajo."""
    devices = sd.query_devices()
    
    # Separar dispositivos de entrada y salida
    input_devices = []
    output_devices = []
    
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            input_devices.append((i, dev['name'], 'entrada'))
        if dev['max_output_channels'] > 0:
            output_devices.append((i, dev['name'], 'salida'))
    
    # Combinar en una lista con separadores
    all_items = []
    all_items.append(("header", "── ENTRADA (micrófono) ──", None))
    all_items.extend(input_devices)
    all_items.append(("header", "── SALIDA (loopback) ──", None))
    all_items.extend(output_devices)
    
    # Filtrar solo dispositivos seleccionables
    selectable = [(i, item) for i, item in enumerate(all_items) if item[0] != "header"]
    
    if not selectable:
        print("No hay dispositivos de audio disponibles.")
        exit(1)
    
    current_idx = 0
    
    while True:
        # Limpiar y mostrar
        print("\033[2J\033[H", end="")  # Clear screen
        print("\n=== Selecciona Dispositivo de Audio ===")
        print("    (↑/↓ para navegar, ENTER para seleccionar, q para salir)\n")
        
        for i, item in enumerate(all_items):
            if item[0] == "header":
                print(f"\n  {item[1]}")
            else:
                # Encontrar si este item está seleccionado
                sel_idx = next((j for j, (idx, _) in enumerate(selectable) if idx == i), None)
                if sel_idx == current_idx:
                    print(f"  → [{item[0]}] {item[1]}")
                else:
                    print(f"    [{item[0]}] {item[1]}")
        
        print("\n")
        
        # Leer tecla
        key = get_key()
        
        if key == '\x1b[A':  # Flecha arriba
            current_idx = max(0, current_idx - 1)
        elif key == '\x1b[B':  # Flecha abajo
            current_idx = min(len(selectable) - 1, current_idx + 1)
        elif key == '\r' or key == '\n':  # Enter
            _, selected_item = selectable[current_idx]
            device_id = selected_item[0]
            device_name = selected_item[1]
            print(f"\n✓ Dispositivo seleccionado: {device_name}\n")
            return device_id
        elif key == 'q' or key == '\x03':  # q o Ctrl+C
            print("\nCancelado.")
            exit(0)
