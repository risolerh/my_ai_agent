let ws;
let audioContext;
let processor;
let stream;
let globalStream;

const SERVICES = {
    httpBase: '',
    wsBase: '',
    modelsPath: '/api/models',
    languagesPath: '/api/languages',
    ollamaModelsPath: '/api/ollama-models',
    streamPath: '/ws/stream'
};

const TTS_CONFIG = {
    bufferSeconds: 0.15
};

function getHttpUrl(path) {
    const base = SERVICES.httpBase || window.location.origin;
    return `${base}${path}`;
}

function getWsUrl(path, params) {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const base = SERVICES.wsBase || `${wsProtocol}//${window.location.host}`;
    const query = params ? `?${params.toString()}` : '';
    return `${base}${path}${query}`;
}

const statusEl = document.getElementById('status');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const logEl = document.getElementById('log');
const inputLangEl = document.getElementById('inputLang');
const outputLangEl = document.getElementById('outputLang');
const agentEnabledEl = document.getElementById('agentEnabled');
const agentModelEl = document.getElementById('agentModel');
const voiceEnabledEl = document.getElementById('voiceEnabled');
const voiceSelectEl = document.getElementById('voiceSelect');
const ttsIndicatorEl = document.getElementById('ttsIndicator');

let currentPartialEl = null;
let ttsContext = null;
let ttsNextTime = 0;
let ttsActiveNodes = [];
let ttsVoices = [];
let ttsIndicatorTimer = null;
let ttsSpeakingUntil = 0;
let inputLangCodeById = {};
let currentInputLangCode = '';

function setControlsDisabled(disabled) {
    inputLangEl.disabled = disabled;
    outputLangEl.disabled = disabled;
    agentEnabledEl.disabled = disabled;
    if (disabled) {
        agentModelEl.disabled = true;
        // Keep SPK toggle available during streaming when agent is enabled.
        voiceEnabledEl.disabled = !agentEnabledEl.checked;
        voiceSelectEl.disabled = true;
    } else {
        agentModelEl.disabled = !agentEnabledEl.checked;
        voiceEnabledEl.disabled = !agentEnabledEl.checked;
        voiceSelectEl.disabled = !agentEnabledEl.checked || !voiceEnabledEl.checked;
    }
}

function setTtsIndicator(state) {
    ttsIndicatorEl.classList.remove('tts-idle', 'tts-speaking', 'tts-muted');
    if (state === 'speaking') {
        ttsIndicatorEl.classList.add('tts-speaking');
    } else if (state === 'muted') {
        ttsIndicatorEl.classList.add('tts-muted');
    } else {
        ttsIndicatorEl.classList.add('tts-idle');
    }
}

function updateTtsIndicatorFromControls() {
    if (!agentEnabledEl.checked) {
        setTtsIndicator('idle');
        return;
    }
    if (!voiceEnabledEl.checked) {
        setTtsIndicator('muted');
        return;
    }
    setTtsIndicator('idle');
}

function normalizeVoices(list) {
    return (list || []).map(item => {
        if (typeof item === 'string') {
            return { code: item, name: item };
        }
        return {
            code: item.code || item.name || '',
            name: item.name || item.code || ''
        };
    }).filter(v => v.code);
}

function updateVoiceOptions() {
    const current = voiceSelectEl.value;
    const targetLang = currentInputLangCode || '';

    voiceSelectEl.innerHTML = '';
    const list = ttsVoices;

    list.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v.code;
        opt.textContent = v.name || v.code;
        voiceSelectEl.appendChild(opt);
    });

    if (current && list.some(v => v.code === current)) {
        voiceSelectEl.value = current;
    }
}

function resetTtsPlayback() {
    ttsActiveNodes.forEach(node => {
        try {
            node.stop();
        } catch (e) {
            // ignore
        }
    });
    ttsActiveNodes = [];
    ttsNextTime = 0;
    ttsSpeakingUntil = 0;
    if (ttsIndicatorTimer) {
        clearTimeout(ttsIndicatorTimer);
        ttsIndicatorTimer = null;
    }
    updateTtsIndicatorFromControls();
}

function ensureTtsContext(sampleRate) {
    if (!ttsContext) {
        ttsContext = new AudioContext({ sampleRate: sampleRate || 16000 });
        return;
    }
    if (sampleRate && ttsContext.sampleRate !== sampleRate) {
        ttsContext.close();
        ttsContext = new AudioContext({ sampleRate });
        ttsNextTime = 0;
        ttsActiveNodes = [];
    }
}

function base64ToArrayBuffer(base64) {
    const binary = atob(base64);
    const buffer = new ArrayBuffer(binary.length);
    const bytes = new Uint8Array(buffer);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return buffer;
}

function isWavBuffer(buffer) {
    const bytes = new Uint8Array(buffer);
    if (bytes.length < 12) return false;
    const riff = String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]);
    const wave = String.fromCharCode(bytes[8], bytes[9], bytes[10], bytes[11]);
    return riff === 'RIFF' && wave === 'WAVE';
}

async function playTtsChunk(base64Data, sampleRate) {
    if (!voiceEnabledEl.checked) return;
    ensureTtsContext(sampleRate || 16000);
    if (ttsContext.state === 'suspended') {
        try {
            await ttsContext.resume();
        } catch (e) {
            // ignore
        }
    }

    const rawBuffer = base64ToArrayBuffer(base64Data);
    let audioBuffer = null;
    if (isWavBuffer(rawBuffer)) {
        try {
            audioBuffer = await ttsContext.decodeAudioData(rawBuffer.slice(0));
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
        audioBuffer = ttsContext.createBuffer(1, float32.length, rate);
        audioBuffer.copyToChannel(float32, 0);
    }

    const source = ttsContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ttsContext.destination);

    const now = ttsContext.currentTime;
    if (ttsNextTime < now + TTS_CONFIG.bufferSeconds) {
        ttsNextTime = now + TTS_CONFIG.bufferSeconds;
    }
    source.start(ttsNextTime);
    ttsNextTime += audioBuffer.duration;

    ttsActiveNodes.push(source);
    source.onended = () => {
        ttsActiveNodes = ttsActiveNodes.filter(n => n !== source);
    };

    setTtsIndicator('speaking');
    ttsSpeakingUntil = Math.max(ttsSpeakingUntil, ttsNextTime);
    if (ttsIndicatorTimer) {
        clearTimeout(ttsIndicatorTimer);
    }
    const remainingMs = Math.max(0, (ttsSpeakingUntil - ttsContext.currentTime) * 1000);
    ttsIndicatorTimer = setTimeout(() => {
        updateTtsIndicatorFromControls();
    }, remainingMs + 50);
}

// Load configuration on startup
window.addEventListener('DOMContentLoaded', async () => {
    try {
        // Fetch/Populate Input Models
        const modelsRes = await fetch(getHttpUrl(SERVICES.modelsPath));
        const models = await modelsRes.json();
        models.forEach(m => {
            // Only show downloaded models
            if (!m.downloaded) return;
            inputLangCodeById[m.id] = m.code || '';

            const opt = document.createElement('option');
            opt.value = m.id;
            opt.textContent = m.lang;

            if (m.id === '2') opt.selected = true; // Default to English Complete (ID 2)
            inputLangEl.appendChild(opt);
        });
        currentInputLangCode = inputLangCodeById[inputLangEl.value] || '';

        // Fetch/Populate Output Languages
        const langsRes = await fetch(getHttpUrl(SERVICES.languagesPath));
        const langs = await langsRes.json();
        langs.forEach(l => {
            const opt = document.createElement('option');
            opt.value = l.code;
            opt.textContent = l.name;
            if (l.code === 'es') opt.selected = true;
            outputLangEl.appendChild(opt);
        });

        const ollamaRes = await fetch(getHttpUrl(SERVICES.ollamaModelsPath));
        if (ollamaRes.ok) {
            const ollamaData = await ollamaRes.json();
            const ollamaModels = ollamaData.models || [];
            const defaultModel = ollamaData.default || "";

            ollamaModels.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = m;
                if (m === defaultModel) opt.selected = true;
                agentModelEl.appendChild(opt);
            });
        }

        const ttsVoicesRes = await fetch(getHttpUrl('/api/tts-voices'));
        if (ttsVoicesRes.ok) {
            const ttsData = await ttsVoicesRes.json();
            const ttsList = ttsData.voices || [];
            ttsVoices = normalizeVoices(ttsList);
            updateVoiceOptions();
        }

        setControlsDisabled(false);
        agentEnabledEl.addEventListener('change', () => {
            if (!agentEnabledEl.disabled) {
                agentModelEl.disabled = !agentEnabledEl.checked;
                if (!agentEnabledEl.checked) {
                    voiceEnabledEl.checked = false;
                }
                voiceEnabledEl.disabled = !agentEnabledEl.checked;
                voiceSelectEl.disabled = !agentEnabledEl.checked || !voiceEnabledEl.checked;
                updateTtsIndicatorFromControls();
            }
        });
        voiceEnabledEl.addEventListener('change', () => {
            if (!voiceEnabledEl.disabled) {
                const controlsLocked = inputLangEl.disabled;
                voiceSelectEl.disabled = controlsLocked || !voiceEnabledEl.checked;
                if (!voiceEnabledEl.checked) {
                    resetTtsPlayback();
                }
                updateTtsIndicatorFromControls();
            }
        });
        inputLangEl.addEventListener('change', () => {
            currentInputLangCode = inputLangCodeById[inputLangEl.value] || '';
            updateVoiceOptions();
        });
        outputLangEl.addEventListener('change', () => {
            updateVoiceOptions();
        });
        updateVoiceOptions();
        updateTtsIndicatorFromControls();

        ttsIndicatorEl.addEventListener('click', () => {
            if (voiceEnabledEl.disabled) {
                return;
            }
            voiceEnabledEl.checked = !voiceEnabledEl.checked;
            voiceEnabledEl.dispatchEvent(new Event('change'));
        });

    } catch (e) {
        console.error("Error loading config", e);
        setStatus("API Error - Ensure Server is Running", "#ffaaaa");
    }
});

function setStatus(msg, color) {
    statusEl.textContent = msg;
    statusEl.style.backgroundColor = color;
}

function setButtonsState(state) {
    if (state === 'connecting') {
        startBtn.disabled = true;
        stopBtn.disabled = false;
        setControlsDisabled(true);
        updateTtsIndicatorFromControls();
    } else if (state === 'streaming') {
        startBtn.disabled = true;
        stopBtn.disabled = false;
        setControlsDisabled(true);
        updateTtsIndicatorFromControls();
    } else {
        startBtn.disabled = false;
        stopBtn.disabled = true;
        setControlsDisabled(false);
        updateTtsIndicatorFromControls();
    }
}

async function startStream() {
    try {
        // Initialize WebSocket with selected languages
        setButtonsState('connecting');
        setStatus('Conectando...', '#fff0aa');
        resetTtsPlayback();
        const inputLang = inputLangEl.value;
        const outputLang = outputLangEl.value;
        const agentEnabled = agentEnabledEl.checked ? 'true' : 'false';
        const agentModel = agentModelEl.value || "";
        const voiceEnabled = voiceEnabledEl.checked ? 'true' : 'false';
        const voiceId = voiceSelectEl.value || "";
        const params = new URLSearchParams({
            input_lang: inputLang,
            output_lang: outputLang,
            agent_enabled: agentEnabled,
            agent_model: agentModel,
            voice_enabled: voiceEnabled,
            voice_id: voiceId
        });
        const url = getWsUrl(SERVICES.streamPath, params);

        console.log("Connecting to", url);
        ws = new WebSocket(url);
        ws.binaryType = 'arraybuffer';

        ws.onopen = () => {
            setStatus('Conectando...', '#fff0aa');
            startAudio();
        };

        ws.onclose = () => {
            stopStream();
        };

        ws.onerror = (e) => {
            console.error("WS Error", e);
            setStatus('Error', '#ffaa00');
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            handleMessage(data);
        };

    } catch (e) {
        console.error(e);
        setButtonsState('stopped');
        setStatus('', '#eee');
        alert("Error starting: " + e.message);
    }
}

async function startAudio() {
    try {
        // Request 16kHz audio specifically
        stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                sampleRate: 16000
            }
        });
        globalStream = stream;

        // Create AudioContext at 16k
        audioContext = new AudioContext({ sampleRate: 16000 });

        // Add the AudioWorklet module
        await audioContext.audioWorklet.addModule('/static/processor.js');

        const source = audioContext.createMediaStreamSource(stream);
        const workletNode = new AudioWorkletNode(audioContext, 'pcm-processor');

        // Handle data from the processor
        workletNode.port.onmessage = (event) => {
            // event.data is the Int16Array buffer
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(event.data);
            }
        };

        source.connect(workletNode);
        workletNode.connect(audioContext.destination);

        // Keep reference to disconnect later if needed (though context close handles it)
        processor = workletNode;
    } catch (e) {
        console.error("Audio access error", e);
        alert("Could not access microphone: " + e.message);
        ws.close();
    }
}

function stopStream() {
    if (globalStream) {
        globalStream.getTracks().forEach(track => track.stop());
    }
    if (audioContext) {
        audioContext.close();
    }
    if (ttsContext) {
        ttsContext.close();
        ttsContext = null;
    }
    if (ws) {
        ws.close();
    }
    resetTtsPlayback();
    setButtonsState('stopped');
    setStatus('', '#eee');
}

function handleMessage(data) {
    if (data.type === 'partial') {
        if (!currentPartialEl) {
            currentPartialEl = document.createElement('div');
            currentPartialEl.className = 'partial';
            logEl.appendChild(currentPartialEl);
        }
        currentPartialEl.textContent = ">> " + data.original;
        logEl.scrollTop = logEl.scrollHeight;
    }
    else if (data.type === 'final') {
        if (currentPartialEl) {
            currentPartialEl.remove();
            currentPartialEl = null;
        }

        const container = document.createElement('div');
        // Dynamic labels based on returned data or selection
        const inLang = data.input_lang || 'SRC';
        const outLang = data.output_lang || 'TGT';

        container.innerHTML = `
            <div class="final"><b>[${inLang.toUpperCase()}]</b> ${data.original} <span style="font-size:0.8em;color:#aaa">(${data.confidence.toFixed(2)})</span></div>
            <div class="translation"><b>[${outLang.toUpperCase()}]</b> ${data.translation}</div>
            <hr/>
        `;
        logEl.appendChild(container);
        logEl.scrollTop = logEl.scrollHeight;
    }
    else if (data.type === 'ready') {
        setButtonsState('streaming');
        if (data.input_lang) {
            currentInputLangCode = data.input_lang;
            updateVoiceOptions();
        }
        setStatus('Conectado', '#aaffaa');
    }
    else if (data.type === 'tts_voices') {
        ttsVoices = normalizeVoices(data.voices || []);
        updateVoiceOptions();
    }
    else if (data.type === 'tts_audio') {
        if (data.data) {
            playTtsChunk(data.data, data.sample_rate).catch(() => { });
        }
    }
    else if (data.type === 'tts_error') {
        const container = document.createElement('div');
        const errorText = data.error || "TTS error";
        container.innerHTML = `
            <div class="agent agent-error"><b>[TTS]</b> ${errorText}</div>
            <hr/>
        `;
        logEl.appendChild(container);
        logEl.scrollTop = logEl.scrollHeight;
    }
    else if (data.type === 'tts_interrupted') {
        resetTtsPlayback();
    }
    else if (data.type === 'agent') {
        const container = document.createElement('div');
        if (data.status === 'ok') {
            container.innerHTML = `
                <div class="agent"><b>[AGENT • ${data.model}]</b> ${data.response}</div>
                <hr/>
            `;
            if (voiceEnabledEl.checked) {
                resetTtsPlayback();
            }
        } else {
            const errorText = data.error || "Agent error";
            container.innerHTML = `
                <div class="agent agent-error"><b>[AGENT • ${data.model}]</b> ${errorText}</div>
                <hr/>
            `;
        }
        logEl.appendChild(container);
        logEl.scrollTop = logEl.scrollHeight;
    }
}

function toggleLog(action) {
    const container = document.getElementById('log-container');

    if (action === 'minimize') {
        if (container.classList.contains('minimized')) {
            container.classList.remove('minimized');
        } else {
            container.classList.add('minimized');
            container.classList.remove('maximized');
        }
    } else if (action === 'maximize') {
        if (container.classList.contains('maximized')) {
            container.classList.remove('maximized');
        } else {
            container.classList.add('maximized');
            container.classList.remove('minimized');
        }
    }

    // Auto-scroll to bottom after transition (approx 300ms)
    setTimeout(() => {
        logEl.scrollTop = logEl.scrollHeight;
    }, 350);
}
