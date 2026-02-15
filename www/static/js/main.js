// Instances
const audioManager = new AudioManager();
const ttsManager = new TTSManager();

const SERVICES = {
    httpBase: '',
    wsBase: '',
    modelsPath: 'api/models',
    languagesPath: 'api/languages',
    ollamaModelsPath: 'api/ollama-models',
    streamPath: 'ws/stream',
    ttVoices: 'api/tts-voices'
};
const SESSION_CONFIG_KEY = 'ai_voice_translator.session_config.v1';

const ws = { current: null }; // Wrapper to hold WS reference
const streamState = {
    starting: false,
    stopping: false
};
const bargeInDetector = new window.BargeInRmsDetector();

function hasActiveSocket() {
    return Boolean(
        ws.current &&
        (ws.current.readyState === WebSocket.CONNECTING || ws.current.readyState === WebSocket.OPEN)
    );
}

function getHttpUrl(path) {
    const base = SERVICES.httpBase;
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

const sessionBtn = document.getElementById('sessionBtn');
const logEl = document.getElementById('log');
const inputLangEl = document.getElementById('inputLang');
const outputLangEl = document.getElementById('outputLang');



let currentPartialEl = null;

let ttsVoices = [];
let inputLangCodeById = {};
let currentInputLangCode = '';

function hasSelectOption(selectEl, value) {
    return Array.from(selectEl.options).some(opt => opt.value === value);
}

function readSessionConfig() {
    try {
        const raw = sessionStorage.getItem(SESSION_CONFIG_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' ? parsed : null;
    } catch (e) {
        return null;
    }
}

function saveSessionConfig() {
    try {
        const payload = {
            inputLang: inputLangEl.value || '2',
            outputLang: outputLangEl.value || 'es',
            agentEnabled: Boolean(agentEnabledEl.checked),
            agentModel: agentModelEl.value || '',
            voiceEnabled: Boolean(voiceEnabledEl.checked),
            voiceId: voiceSelectEl.value || ''
        };
        sessionStorage.setItem(SESSION_CONFIG_KEY, JSON.stringify(payload));
    } catch (e) {
        // Ignore storage failures (private mode/quota/security settings).
    }
}

function syncAgentVoiceControls() {
    agentModelEl.disabled = !agentEnabledEl.checked;
    if (!agentEnabledEl.checked) {
        voiceEnabledEl.checked = false;
    }
    voiceEnabledEl.disabled = !agentEnabledEl.checked;
    const controlsLocked = inputLangEl.disabled;
    voiceSelectEl.disabled = controlsLocked || !agentEnabledEl.checked || !voiceEnabledEl.checked;
}

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
        syncAgentVoiceControls();
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

function clearSessionTranscriptView() {
    logEl.innerHTML = '';
    currentPartialEl = null;
    if (typeof resetMessageHistoryState === 'function') {
        resetMessageHistoryState();
    }
}

function clearConversationHistory() {
    clearSessionTranscriptView();

    const socket = ws.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
        return;
    }

    try {
        socket.send(JSON.stringify({ type: 'clear_conversation_history' }));
    } catch (e) {
        console.error('Failed to clear conversation history', e);
        setStatus('Clear failed', '#ffd4d4');
    }
}

async function playTtsChunk(base64Data, sampleRate, meta = {}) {
    if (!voiceEnabledEl.checked) return;
    await ttsManager.playChunk(base64Data, sampleRate, meta);
}

function sendImmediateBargeIn(threshold) {
    const socket = ws.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;

    const stats = ttsManager.getPlaybackStats();
    resetTtsPlayback();
    setStatus('Interrumpido', '#ffe7c2');

    try {
        socket.send(JSON.stringify({
            type: 'barge_in',
            barge_in_threshold: Number(threshold.toFixed(4)),
            ...stats
        }));
    } catch (e) {
        console.warn('barge_in send failed', e);
    }
}

function maybeTriggerBargeIn(int16Data) {
    const result = bargeInDetector.process(int16Data, ttsManager.isSpeaking());

    if (typeof updateBargeInVisualizer === 'function') {
        updateBargeInVisualizer({
            rms: result.rms,
            threshold: result.threshold,
            visMax: result.visMax,
            state: result.state
        });
    }

    if (result.triggered) {
        sendImmediateBargeIn(result.threshold);
    }
}

// Load configuration on startup
window.addEventListener('DOMContentLoaded', async () => {
    const savedConfig = readSessionConfig();
    if (savedConfig && typeof savedConfig.agentEnabled === 'boolean') {
        agentEnabledEl.checked = savedConfig.agentEnabled;
    }
    if (savedConfig && typeof savedConfig.voiceEnabled === 'boolean') {
        voiceEnabledEl.checked = savedConfig.voiceEnabled;
    }

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
        if (savedConfig?.inputLang && hasSelectOption(inputLangEl, savedConfig.inputLang)) {
            inputLangEl.value = savedConfig.inputLang;
        }
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
        if (savedConfig?.outputLang && hasSelectOption(outputLangEl, savedConfig.outputLang)) {
            outputLangEl.value = savedConfig.outputLang;
        }

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
        if (savedConfig?.agentModel && hasSelectOption(agentModelEl, savedConfig.agentModel)) {
            agentModelEl.value = savedConfig.agentModel;
        }

        const ttsVoicesRes = await fetch(getHttpUrl(SERVICES.ttVoices));
        if (ttsVoicesRes.ok) {
            const ttsData = await ttsVoicesRes.json();
            const ttsList = ttsData.voices || [];
            ttsVoices = normalizeVoices(ttsList);
            updateVoiceOptions();
            if (savedConfig?.voiceId && hasSelectOption(voiceSelectEl, savedConfig.voiceId)) {
                voiceSelectEl.value = savedConfig.voiceId;
            }
        }

        setControlsDisabled(false);
        syncAgentVoiceControls();

        agentEnabledEl.addEventListener('change', () => {
            if (!agentEnabledEl.disabled) {
                syncAgentVoiceControls();
                saveSessionConfig();
            }
        });
        voiceEnabledEl.addEventListener('change', () => {
            if (!voiceEnabledEl.disabled) {
                if (!voiceEnabledEl.checked) {
                    resetTtsPlayback();
                }
                syncAgentVoiceControls();
                saveSessionConfig();
            }
        });
        agentModelEl.addEventListener('change', () => {
            saveSessionConfig();
        });
        voiceSelectEl.addEventListener('change', () => {
            saveSessionConfig();
        });
        inputLangEl.addEventListener('change', () => {
            currentInputLangCode = inputLangCodeById[inputLangEl.value] || '';
            updateVoiceOptions();
            saveSessionConfig();
        });
        outputLangEl.addEventListener('change', () => {
            updateVoiceOptions();
            saveSessionConfig();
        });
        updateVoiceOptions();
        saveSessionConfig();

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
        sessionBtn.disabled = false;
        sessionBtn.textContent = 'End Session';
        sessionBtn.classList.add('is-stop');
        muteBtn.disabled = false;
        setControlsDisabled(true);
    } else if (state === 'streaming') {
        sessionBtn.disabled = false;
        sessionBtn.textContent = 'End Session';
        sessionBtn.classList.add('is-stop');
        muteBtn.disabled = false;
        setControlsDisabled(true);
    } else {
        sessionBtn.disabled = false;
        sessionBtn.textContent = 'Start Session';
        sessionBtn.classList.remove('is-stop');
        muteBtn.disabled = true;
        setControlsDisabled(false);
    }
}

function toggleSession() {
    if (streamState.starting || streamState.stopping) {
        return;
    }
    if (hasActiveSocket() || audioManager.isActive()) {
        stopStream();
        return;
    }
    startStream();
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
                maybeTriggerBargeIn(data);
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
    bargeInDetector.reset();
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
