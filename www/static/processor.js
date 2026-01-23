/**
 * PCMProcessor matches the interface required by AudioWorkletProcessor.
 * 
 * Purpose:
 * This processor runs in a separate audio thread (AudioWorklet) to prevent blocking the main UI thread.
 * It receives raw audio samples (Float32) from the browser's microphone input and converts them 
 * into 16-bit PCM Integer format (Int16), which is the binary format expected by the STT API server.
 * 
 * It buffers the data and sends it back to the main thread via the message port once the buffer is full.
 */
class PCMProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.bufferSize = 4096;
        this.buffer = new Int16Array(this.bufferSize);
        this.bufferIndex = 0;
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (input && input.length > 0) {
            const inputChannel = input[0];

            for (let i = 0; i < inputChannel.length; i++) {
                // Convert Float32 [-1.0, 1.0] to Int16 [-32768, 32767]
                let s = Math.max(-1, Math.min(1, inputChannel[i]));
                this.buffer[this.bufferIndex++] = s < 0 ? s * 0x8000 : s * 0x7FFF;

                // If buffer is full, flush it
                if (this.bufferIndex >= this.bufferSize) {
                    this.port.postMessage(this.buffer.slice(0, this.bufferSize));
                    this.bufferIndex = 0;
                }
            }
        }
        return true;
    }
}

registerProcessor('pcm-processor', PCMProcessor);
