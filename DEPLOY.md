# Despliegue

## Requisitos previos
- Python 3.8+
- Dispositivo de audio configurado

## Instalación

```bash
# Dependencias del sistema (Ubuntu/Debian)
sudo apt install python3.12-venv libportaudio2 portaudio19-dev python3-tk pavucontrol -y

# Crear entorno virtual
python3 -m venv venv
source ./venv/bin/activate

# Instalar uv (instalador rápido) y dependencias
pip install uv
uv pip install -r requirements.txt
```

## Ejecutar

```bash
source ./venv/bin/activate
python main.py
```

Al iniciar:
1. Selecciona el modelo Vosk (se descarga automáticamente si no existe)
2. Selecciona el dispositivo de audio (↑/↓ para navegar, ENTER para seleccionar)

## Configurar Loopback (capturar audio del sistema)

Para transcribir audio que sale por las bocinas:

1. Ejecuta `python main.py`
2. Selecciona dispositivo **pulse** de la sección ENTRADA
3. Abre `pavucontrol` en otra terminal
4. Ve a pestaña **Recording**
5. Encuentra la app Python y cambia su fuente a **"Monitor of [tu salida]"**

Esto redirige el audio del sistema a la aplicación.
