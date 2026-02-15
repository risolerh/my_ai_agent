/**
 * AudioManager.js
 * Handles microphone access, AudioContext, and AudioWorklet setup.
 */

URL_PROCESSOR = 'static/js/pcm-processor.js';

class AudioManager {
    constructor() {
        this.stream = null;
        this.audioContext = null;
        this.processor = null;
        this.sourceNode = null;
        this.monitorGain = null;
        this.isStarting = false;
        this.onAudioDataCallback = null;
    }

    /**
     * Starts audio capture and processing.
     * @param {Function} onAudioDataCallback - Function to call when audio data is ready (Int16Array).
     * @param {Object} visualizerCallback - Optional function to initialize visualizer.
     */
    async start(onAudioDataCallback, visualizerCallback) {
        if (this.isStarting || this.stream || this.audioContext) {
            return false;
        }

        this.isStarting = true;
        this.onAudioDataCallback = onAudioDataCallback;

        try {
            // Request 16kHz audio specifically
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    sampleRate: 16000,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });

            // Create AudioContext at 16k
            this.audioContext = new AudioContext({ sampleRate: 16000 });

            // Add the AudioWorklet module
            await this.audioContext.audioWorklet.addModule(URL_PROCESSOR);

            const source = this.audioContext.createMediaStreamSource(this.stream);
            const workletNode = new AudioWorkletNode(this.audioContext, 'pcm-processor');

            // Handle data from the processor
            workletNode.port.onmessage = (event) => {
                // event.data is the Int16Array buffer
                if (this.onAudioDataCallback) {
                    this.onAudioDataCallback(event.data);
                }
            };

            source.connect(workletNode);
            // Keep graph alive without monitoring mic to speakers (prevents acoustic feedback loops).
            this.monitorGain = this.audioContext.createGain();
            this.monitorGain.gain.value = 0;
            workletNode.connect(this.monitorGain);
            this.monitorGain.connect(this.audioContext.destination);

            // Initialize visualizer if provided
            if (visualizerCallback && typeof visualizerCallback === 'function') {
                visualizerCallback(this.stream, this.audioContext, source);
            }

            this.processor = workletNode;
            this.sourceNode = source;
            return true;

        } catch (e) {
            console.error("Audio access error", e);
            this.stop();
            throw e;
        } finally {
            this.isStarting = false;
        }
    }

    /**
     * Stops audio capture and closes context.
     */
    stop() {
        if (this.processor) {
            try {
                this.processor.port.onmessage = null;
                this.processor.disconnect();
            } catch (_) { }
        }
        if (this.sourceNode) {
            try {
                this.sourceNode.disconnect();
            } catch (_) { }
            this.sourceNode = null;
        }
        if (this.monitorGain) {
            try {
                this.monitorGain.disconnect();
            } catch (_) { }
            this.monitorGain = null;
        }
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        if (this.audioContext) {
            this.audioContext.close().catch(() => { });
            this.audioContext = null;
        }
        this.processor = null; // Processor is disconnected when context closes
        this.onAudioDataCallback = null;
        this.isStarting = false;
    }

    isActive() {
        return this.isStarting || this.stream !== null || this.audioContext !== null;
    }

    /**
     * Toggles microphone mute state.
     * @returns {boolean} - True if enabled (unmuted), false if disabled (muted).
     */
    toggleMute() {
        if (this.stream) {
            const track = this.stream.getAudioTracks()[0];
            track.enabled = !track.enabled;
            return track.enabled;
        }
        return false;
    }
}
