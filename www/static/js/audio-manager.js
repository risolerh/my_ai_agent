/**
 * AudioManager.js
 * Handles microphone access, AudioContext, and AudioWorklet setup.
 */
class AudioManager {
    constructor() {
        this.stream = null;
        this.audioContext = null;
        this.processor = null;
        this.onAudioDataCallback = null;
    }

    /**
     * Starts audio capture and processing.
     * @param {Function} onAudioDataCallback - Function to call when audio data is ready (Int16Array).
     * @param {Object} visualizerCallback - Optional function to initialize visualizer.
     */
    async start(onAudioDataCallback, visualizerCallback) {
        this.onAudioDataCallback = onAudioDataCallback;

        try {
            // Request 16kHz audio specifically
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    sampleRate: 16000
                }
            });

            // Create AudioContext at 16k
            this.audioContext = new AudioContext({ sampleRate: 16000 });

            // Add the AudioWorklet module
            await this.audioContext.audioWorklet.addModule('/static/js/processor.js');

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
            workletNode.connect(this.audioContext.destination);

            // Initialize visualizer if provided
            if (visualizerCallback && typeof visualizerCallback === 'function') {
                visualizerCallback(this.stream, this.audioContext, source);
            }

            this.processor = workletNode;
            return true;

        } catch (e) {
            console.error("Audio access error", e);
            throw e;
        }
    }

    /**
     * Stops audio capture and closes context.
     */
    stop() {
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }
        this.processor = null; // Processor is disconnected when context closes
        this.onAudioDataCallback = null;
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
