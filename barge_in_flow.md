# Actores y Flujo de Interacción (Barge-In)

Este documento detalla los actores del sistema y el flujo actualizado de interacción, incluyendo la lógica de interrupción (Barge-In) y la gestión de turnos por silencio.

## 👥 Actores y Funciones

| Actor | Componente | Función Principal |
| :--- | :--- | :--- |
| **SOCKET IN** | `server.py` (WebSocket) | Recibe el stream de audio raw desde el cliente (navegador/móvil). |
| **STT** | `GrpcSttStrategy` | Procesa el audio y emite transcripciones parciales y finales. |
| **ORQUESTADOR** | `AudioService` | Cerebro del sistema. Gestiona timers de silencio, historial y estados. |
| **LLM** | `OllamaClient` | Genera las respuestas de texto (Inteligencia Artificial). |
| **TTS** | `TTSStreamService` | Convierte texto a voz y rastrea qué segmentos se han reproducido. |
| **SOCKET OUT** | `server.py` | Envía audio (TTS) y eventos de estado al cliente. |

---

## 🔄 Flujo de Conversación (Turn-Taking)

Para evitar respuestas fragmentadas, el sistema utiliza una lógica de acumulación basada en silencio.

1.  **Entrada de Voz**: El usuario habla. **SOCKET IN** recibe audio y **STT** genera texto.
2.  **Acumulación**: **ORQUESTADOR** recibe el texto y lo guarda en un buffer temporal.
3.  **Timer de Silencio**: Se inicia una cuenta regresiva de **4.0 segundos**.
    *   *Si el usuario habla de nuevo antes de los 4s*: El timer se reinicia y el texto se añade al buffer.
4.  **Disparo (Flush)**: Solo cuando hay silencio por 4 segundos completos, el **ORQUESTADOR** envía todo el buffer acumulado al **LLM**.

---

## 🛑 Flujo de Barge-In (Interrupción)

Este flujo se activa cuando el sistema detecta que el usuario habla **mientras** el TTS está reproduciendo audio.

### 1. Detección
*   **STT** detecta texto parcial o final.
*   **ORQUESTADOR** verifica si `_tts_speaking == True` O si `_is_agent_generating == True` (LLM escribiendo).

### 2. Ejecución Inmediata
El **ORQUESTADOR** ejecuta `barge_in()`:
*   **Cancela Timers**: Detiene cualquier espera de turno pendiente.
*   **Recuperación**: Si el LLM estaba generando una respuesta, se recupera el prompt original y se vuelve a cola de entrada.
*   **Cancela LLM**: Corta la conexión HTTP con **LLM** si aún estaba generando texto.
*   **Limpia Colas**: Elimina mensajes pendientes de procesar.
*   **Notifica al Server**: Llama al callback de interrupción.

### 3. Detención Crítica (TTS)
El **TTS** recibe la orden de parar:
1.  **Captura Contexto**: Identifica exactamente hasta qué palabra escuchó el usuario (`spoken_text`).
2.  **Stop**: Detiene la reproducción de audio inmediatamente y limpia su buffer.

### 4. Actualización de Historial
El **ORQUESTADOR** registra la interacción especial:
*   Guarda la respuesta completa que el LLM había generado.
*   Marca la entrada como `interrupted: True`.
*   Registra el `spoken_text` (lo que el usuario oyó) vs lo que se perdió.

### 5. Recuperación
El sistema vuelve al estado de **Acumulación** para escuchar la nueva orden del usuario (la que causó la interrupción).
Al enviar el nuevo prompt al **LLM**, se le instruye:
> *"Tu respuesta anterior fue interrumpida. El usuario escuchó hasta: '...'. Responde a su nueva petición."*
