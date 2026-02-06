
let visualizerCtx = {
    frame: null,
    analyser: null,
    stream: null,
    bar: document.getElementById('visualizerBar'),
    muteBtn: document.getElementById('muteBtn')
};

function initVisualizer(stream, audioContext, source) {
    if (!visualizerCtx.bar) visualizerCtx.bar = document.getElementById('visualizerBar');
    if (!visualizerCtx.muteBtn) visualizerCtx.muteBtn = document.getElementById('muteBtn');

    visualizerCtx.stream = stream;

    // Create Analyser
    visualizerCtx.analyser = audioContext.createAnalyser();
    visualizerCtx.analyser.fftSize = 256;

    // Connect source to analyser
    // Note: source is already connected to worklet in main.js, we fan out here
    source.connect(visualizerCtx.analyser);

    drawVisualizer();
}

function stopVisualizer() {
    if (visualizerCtx.frame) {
        cancelAnimationFrame(visualizerCtx.frame);
        visualizerCtx.frame = null;
    }
    if (visualizerCtx.bar) {
        visualizerCtx.bar.style.height = '0%';
    }
    visualizerCtx.stream = null;
    visualizerCtx.analyser = null;

    // Reset mute button state visually if needed, though main.js handles disabling
    if (visualizerCtx.muteBtn) {
        visualizerCtx.muteBtn.textContent = '🎤 On';
        visualizerCtx.muteBtn.classList.remove('muted');
    }
}

function toggleMute() {
    if (visualizerCtx.stream) {
        const track = visualizerCtx.stream.getAudioTracks()[0];
        track.enabled = !track.enabled;

        const btn = visualizerCtx.muteBtn;
        if (track.enabled) {
            btn.textContent = '🎤 On';
            btn.classList.remove('muted');
        } else {
            btn.textContent = '🎤 Off';
            btn.classList.add('muted');
        }
    }
}

function drawVisualizer() {
    if (!visualizerCtx.analyser) return;

    const dataArray = new Uint8Array(visualizerCtx.analyser.frequencyBinCount);
    visualizerCtx.analyser.getByteFrequencyData(dataArray);

    // Calculate average volume
    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
        sum += dataArray[i];
    }
    const average = sum / dataArray.length;

    // Scale for visual effect
    const height = Math.min(100, (average / 100) * 100 * 1.5);

    if (visualizerCtx.bar) {
        visualizerCtx.bar.style.height = `${height}%`;
    }

    visualizerCtx.frame = requestAnimationFrame(drawVisualizer);
}
