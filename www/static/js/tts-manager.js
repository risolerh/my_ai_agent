/**
 * TTSManager.js
 * Handles text-to-speech audio queuing and playback.
 */
class TTSManager {
    constructor() {
        this.context = null;
        this.playQueue = [];
        this.activeNodes = [];
        this.nextPlayTime = 0;
        this.bufferSeconds = 0.15;
    }

    /**
     * Ensures AudioContext is ready and running.
     * @param {number} sampleRate 
     */
    _ensureContext(sampleRate) {
        if (!this.context) {
            this.context = new AudioContext({ sampleRate: sampleRate || 16000 });
            return;
        }
        if (sampleRate && this.context.sampleRate !== sampleRate) {
            this.context.close();
            this.context = new AudioContext({ sampleRate });
            this.nextPlayTime = 0;
            this.activeNodes = [];
        }
    }

    /**
     * Resets playback queue and stops current audio.
     */
    reset() {
        this.activeNodes.forEach(node => {
            try {
                node.stop();
            } catch (e) {
                // ignore
            }
        });
        this.activeNodes = [];
        this.playQueue = [];
        this.nextPlayTime = 0;
    }

    /**
     * Closes the audio context completely.
     */
    close() {
        if (this.context) {
            this.context.close();
        }
        this.context = null;
        this.reset();
    }

    /**
     * Plays a base64 encoded audio chunk.
     * @param {string} base64Data - Base64 encoded audio data (WAV or raw PCM).
     * @param {number} sampleRate - Sample rate of the audio data.
     */
    async playChunk(base64Data, sampleRate) {
        this._ensureContext(sampleRate || 16000);
        
        if (this.context.state === 'suspended') {
            try {
                await this.context.resume();
            } catch (e) {
                // ignore
            }
        }

        const rawBuffer = this._base64ToArrayBuffer(base64Data);
        let audioBuffer = null;

        if (this._isWavBuffer(rawBuffer)) {
            try {
                audioBuffer = await this.context.decodeAudioData(rawBuffer.slice(0));
            } catch (e) {
                console.error('TTS WAV decode error', e);
                return;
            }
        } else {
            const int16 = new Int16Array(rawBuffer);
            const float32 = new Float32Array(int16.length);
            for (let i = 0; i < int16.length; i++) {
                float32[i] = int16[i] / 32768;
            }
            const rate = sampleRate || 16000;
            audioBuffer = this.context.createBuffer(1, float32.length, rate);
            audioBuffer.copyToChannel(float32, 0);
        }

        const source = this.context.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(this.context.destination);

        const now = this.context.currentTime;
        if (this.nextPlayTime < now + this.bufferSeconds) {
            this.nextPlayTime = now + this.bufferSeconds;
        }

        source.start(this.nextPlayTime);
        this.nextPlayTime += audioBuffer.duration;

        this.activeNodes.push(source);
        source.onended = () => {
            this.activeNodes = this.activeNodes.filter(n => n !== source);
        };
    }

    _base64ToArrayBuffer(base64) {
        const binary = atob(base64);
        const buffer = new ArrayBuffer(binary.length);
        const bytes = new Uint8Array(buffer);
        for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        return buffer;
    }

    _isWavBuffer(buffer) {
        const bytes = new Uint8Array(buffer);
        if (bytes.length < 12) return false;
        const riff = String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]);
        const wave = String.fromCharCode(bytes[8], bytes[9], bytes[10], bytes[11]);
        return riff === 'RIFF' && wave === 'WAVE';
    }
}
