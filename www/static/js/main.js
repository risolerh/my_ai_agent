// Instances
const audioManager = new AudioManager();
const ttsManager = new TTSManager();

const SERVICES = {
    httpBase: '',
    wsBase: '',
    modelsPath: '/api/models',
    languagesPath: '/api/languages',
    ollamaModelsPath: '/api/ollama-models',
    streamPath: '/ws/stream'
};

const ws = { current: null }; // Wrapper to hold WS reference
const streamState = {
    starting: false,
    stopping: false
};

function hasActiveSocket() {
    return Boolean(
        ws.current &&
        (ws.current.readyState === WebSocket.CONNECTING || ws.current.readyState === WebSocket.OPEN)
    );
}

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
const agentEnabledEl = document.getElementById('agentEnabled');
const agentModelEl = document.getElementById('agentModel');
const voiceEnabledEl = document.getElementById('voiceEnabled');
const voiceSelectEl = document.getElementById('voiceSelect');

const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const logEl = document.getElementById('log');
const inputLangEl = document.getElementById('inputLang');
const outputLangEl = document.getElementById('outputLang');



let currentPartialEl = null;

let ttsVoices = [];
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
    ttsManager.reset();
}

async function playTtsChunk(base64Data, sampleRate) {
    if (!voiceEnabledEl.checked) return;
    await ttsManager.playChunk(base64Data, sampleRate);
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
            }
        });
        voiceEnabledEl.addEventListener('change', () => {
            if (!voiceEnabledEl.disabled) {
                const controlsLocked = inputLangEl.disabled;
                voiceSelectEl.disabled = controlsLocked || !voiceEnabledEl.checked;
                if (!voiceEnabledEl.checked) {
                    resetTtsPlayback();
                }
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
        muteBtn.disabled = false;
        setControlsDisabled(true);
    } else if (state === 'streaming') {
        startBtn.disabled = true;
        stopBtn.disabled = false;
        muteBtn.disabled = false;
        setControlsDisabled(true);
    } else {
        startBtn.disabled = false;
        stopBtn.disabled = true;

        setControlsDisabled(false);
    }
}

async function startStream() {
    if (streamState.starting || streamState.stopping || hasActiveSocket() || audioManager.isActive()) {
        return;
    }

    streamState.starting = true;

    try {
        // Unlock TTS audio context while we are still in a user gesture.
        try {
            await ttsManager.prepare(16000);
        } catch (e) {
            console.warn('[TTS] prepare failed:', e?.message || e);
        }

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
        const socket = new WebSocket(url);
        socket.binaryType = 'arraybuffer';
        ws.current = socket;

        socket.onopen = () => {
            if (ws.current !== socket) {
                socket.close();
                return;
            }
            setStatus('Conectando...', '#fff0aa');
            startAudio(socket);
        };

        socket.onclose = () => {
            if (ws.current !== socket) return;
            stopStream(true);
        };

        socket.onerror = (e) => {
            console.error("WS Error", e);
            setStatus('Error', '#ffaa00');
        };

        socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            handleMessage(data);
        };

    } catch (e) {
        console.error(e);
        setButtonsState('stopped');
        setStatus('', '#eee');
        alert("Error starting: " + e.message);
    } finally {
        streamState.starting = false;
    }
}

async function startAudio(socket) {
    if (!socket || ws.current !== socket || audioManager.isActive()) {
        return;
    }

    try {
        await audioManager.start(
            (data) => {
                if (ws.current === socket && socket.readyState === WebSocket.OPEN) {
                    socket.send(data);
                }
            },
            (stream, context, source) => {
                // Initialize visualizer
                if (typeof initVisualizer === 'function') {
                    initVisualizer(stream, context, source);
                }
            }
        );
    } catch (e) {
        alert("Could not access microphone: " + e.message);
        if (ws.current === socket) socket.close();
    }
}

function stopStream(fromSocketClose = false) {
    if (streamState.stopping) {
        return;
    }
    streamState.stopping = true;

    audioManager.stop();
    ttsManager.close();

    const socket = ws.current;
    ws.current = null;
    if (socket && !fromSocketClose) {
        socket.onclose = null;
        socket.onerror = null;
        socket.onmessage = null;
        if (socket.readyState === WebSocket.CONNECTING || socket.readyState === WebSocket.OPEN) {
            socket.close();
        }
    }
    resetTtsPlayback(); 
    if (typeof stopVisualizer === 'function') {
        stopVisualizer();
    }
    setButtonsState('stopped');
    setStatus('', '#eee');
    streamState.starting = false;
    streamState.stopping = false;
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

function toggleMute() {
    const isEnabled = audioManager.toggleMute();
    if (isEnabled) {
        muteBtn.textContent = '🎤 On';
        muteBtn.classList.remove('muted');
    } else {
        muteBtn.textContent = '🎤 Muted';
        muteBtn.classList.add('muted');
    }
}
