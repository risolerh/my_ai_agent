
let visualizerCtx = {
    frame: null,
    analyser: null,
    stream: null,
    bar: document.getElementById('visualizerBar'),
    thresholdLine: document.getElementById('visualizerThreshold'),
    rmsText: document.getElementById('audioRmsText'),
    gateText: document.getElementById('audioGateText'),
    stateText: document.getElementById('audioStateText'),
    muteBtn: document.getElementById('muteBtn')
};

function initVisualizer(stream, audioContext, source) {
    if (!visualizerCtx.bar) visualizerCtx.bar = document.getElementById('visualizerBar');
    if (!visualizerCtx.thresholdLine) visualizerCtx.thresholdLine = document.getElementById('visualizerThreshold');
    if (!visualizerCtx.rmsText) visualizerCtx.rmsText = document.getElementById('audioRmsText');
    if (!visualizerCtx.gateText) visualizerCtx.gateText = document.getElementById('audioGateText');
    if (!visualizerCtx.stateText) visualizerCtx.stateText = document.getElementById('audioStateText');
    if (!visualizerCtx.muteBtn) visualizerCtx.muteBtn = document.getElementById('muteBtn');

    visualizerCtx.stream = stream;

    // Create Analyser
    visualizerCtx.analyser = audioContext.createAnalyser();
    visualizerCtx.analyser.fftSize = 256;

    // Connect source to analyser
    // Note: source is already connected to worklet in main.js, we fan out here
    source.connect(visualizerCtx.analyser);

    updateBargeInVisualizer({
        rms: 0,
        threshold: 0.014,
        visMax: 0.05,
        state: "silence"
    });
}

function stopVisualizer() {
    if (visualizerCtx.frame) {
        cancelAnimationFrame(visualizerCtx.frame);
        visualizerCtx.frame = null;
    }
    if (visualizerCtx.bar) {
        visualizerCtx.bar.style.height = '0%';
    }
    if (visualizerCtx.thresholdLine) {
        visualizerCtx.thresholdLine.style.bottom = '0%';
    }
    if (visualizerCtx.rmsText) {
        visualizerCtx.rmsText.textContent = 'RMS 0.000';
    }
    if (visualizerCtx.gateText) {
        visualizerCtx.gateText.textContent = 'Gate 0.014';
    }
    if (visualizerCtx.stateText) {
        visualizerCtx.stateText.textContent = 'silence';
        visualizerCtx.stateText.classList.remove('state-near', 'state-trigger');
        visualizerCtx.stateText.classList.add('state-silence');
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

function updateBargeInVisualizer({ rms, threshold, visMax, state }) {
    const maxValue = Math.max(visMax || 0.05, 0.005);
    const safeRms = Math.max(0, Number(rms || 0));
    const safeThreshold = Math.max(0, Number(threshold || 0.014));
    const levelPercent = Math.max(0, Math.min(100, (safeRms / maxValue) * 100));
    const thresholdPercent = Math.max(0, Math.min(100, (safeThreshold / maxValue) * 100));

    if (visualizerCtx.bar) {
        visualizerCtx.bar.style.height = `${levelPercent}%`;
        if (levelPercent < 40) {
            visualizerCtx.bar.style.background = '#4caf50';
        } else if (levelPercent < 70) {
            visualizerCtx.bar.style.background = '#f9a825';
        } else {
            visualizerCtx.bar.style.background = '#e53935';
        }
    }
    if (visualizerCtx.thresholdLine) {
        visualizerCtx.thresholdLine.style.bottom = `${thresholdPercent}%`;
    }
    if (visualizerCtx.rmsText) {
        visualizerCtx.rmsText.textContent = `RMS ${safeRms.toFixed(3)}`;
    }
    if (visualizerCtx.gateText) {
        visualizerCtx.gateText.textContent = `Gate ${safeThreshold.toFixed(3)}`;
    }
    if (visualizerCtx.stateText) {
        const displayState = state || 'silence';
        visualizerCtx.stateText.textContent = displayState;
        visualizerCtx.stateText.classList.remove('state-silence', 'state-near', 'state-trigger');
        if (displayState === 'trigger') {
            visualizerCtx.stateText.classList.add('state-trigger');
        } else if (displayState === 'near') {
            visualizerCtx.stateText.classList.add('state-near');
        } else {
            visualizerCtx.stateText.classList.add('state-silence');
        }
    }
}
