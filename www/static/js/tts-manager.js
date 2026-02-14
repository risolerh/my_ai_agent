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
        this.preferredSampleRate = 16000;
        this.chunkTimeline = [];
        this.totalAudioSeconds = 0;
        this.totalTextChars = 0;
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
     * Prepare AudioContext from a user gesture to avoid autoplay blocking.
     * @param {number} sampleRate
     */
    async prepare(sampleRate) {
        this._ensureContext(sampleRate || this.preferredSampleRate);
        if (this.context && this.context.state === 'suspended') {
            await this.context.resume();
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
        this.chunkTimeline = [];
        this.totalAudioSeconds = 0;
        this.totalTextChars = 0;
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
    async playChunk(base64Data, sampleRate, meta = {}) {
        this._ensureContext(sampleRate || 16000);
        
        if (this.context.state === 'suspended') {
            try {
                await this.context.resume();
            } catch (e) {
                console.warn(`[TTS] AudioContext resume blocked: ${e.message}`);
                return;
            }
        }

        const rawBuffer = this._base64ToArrayBuffer(base64Data);
        let audioBuffer = null;

        try {
            // Attempt to decode as WAV, OGG, MP3, etc.
            const tempBuffer = rawBuffer.slice(0);
            audioBuffer = await this.context.decodeAudioData(tempBuffer);
            console.log(`[TTS] Decoded audio: ${audioBuffer.duration.toFixed(2)}s, channels: ${audioBuffer.numberOfChannels}, rate: ${audioBuffer.sampleRate}`);
        } catch (e) {
            console.warn(`[TTS] decodeAudioData failed, trying manual PCM fallback. Error: ${e.message}`);
            // Fallback: Assume Raw PCM 16-bit
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

        const startAt = this.nextPlayTime;
        source.start(startAt);
        this.nextPlayTime += audioBuffer.duration;

        const text = typeof meta.text === 'string' ? meta.text : '';
        const chunkMeta = {
            startAt,
            duration: audioBuffer.duration,
            textChars: text.length,
            ended: false
        };
        this.chunkTimeline.push(chunkMeta);
        this.totalAudioSeconds += audioBuffer.duration;
        this.totalTextChars += text.length;

        this.activeNodes.push(source);
        source.onended = () => {
            this.activeNodes = this.activeNodes.filter(n => n !== source);
            chunkMeta.ended = true;
        };
    }

    isSpeaking() {
        if (!this.context) return false;
        const now = this.context.currentTime;
        return this.activeNodes.length > 0 || this.nextPlayTime > (now + 0.01);
    }

    getPlaybackStats() {
        if (!this.context || this.chunkTimeline.length === 0) {
            return {
                played_audio_seconds: 0,
                total_audio_seconds: 0,
                playback_percent: 0,
                played_text_percent: 0
            };
        }

        const now = this.context.currentTime;
        let playedAudioSeconds = 0;
        let playedTextChars = 0;

        for (const chunk of this.chunkTimeline) {
            const chunkEnd = chunk.startAt + chunk.duration;
            if (chunk.ended || now >= chunkEnd) {
                playedAudioSeconds += chunk.duration;
                playedTextChars += chunk.textChars;
                continue;
            }
            if (now > chunk.startAt) {
                const ratio = Math.max(0, Math.min(1, (now - chunk.startAt) / chunk.duration));
                playedAudioSeconds += chunk.duration * ratio;
                playedTextChars += chunk.textChars * ratio;
            }
        }

        const totalAudioSeconds = Math.max(this.totalAudioSeconds, 0);
        const playbackPercent = totalAudioSeconds > 0
            ? (playedAudioSeconds / totalAudioSeconds) * 100
            : 0;
        const playedTextPercent = this.totalTextChars > 0
            ? (playedTextChars / this.totalTextChars) * 100
            : 0;

        return {
            played_audio_seconds: Number(playedAudioSeconds.toFixed(3)),
            total_audio_seconds: Number(totalAudioSeconds.toFixed(3)),
            playback_percent: Number(Math.max(0, Math.min(100, playbackPercent)).toFixed(1)),
            played_text_percent: Number(Math.max(0, Math.min(100, playedTextPercent)).toFixed(1))
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

}
