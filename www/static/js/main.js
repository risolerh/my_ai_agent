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
        console.log("Connecting to", url);
        ws.current = new WebSocket(url);
        ws.current.binaryType = 'arraybuffer';

        ws.current.onopen = () => {
            setStatus('Conectando...', '#fff0aa');
            startAudio();
        };

        ws.current.onclose = () => {
            stopStream();
        };

        ws.current.onerror = (e) => {
            console.error("WS Error", e);
            setStatus('Error', '#ffaa00');
        };

        ws.current.onmessage = (event) => {
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
        await audioManager.start(
            (data) => {
                if (ws.current && ws.current.readyState === WebSocket.OPEN) {
                    ws.current.send(data);
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
        if (ws.current) ws.current.close();
    }
}

function stopStream() {
    audioManager.stop();
    ttsManager.close();

    if (ws.current) {
        ws.current.close();
        ws.current = null;
    }
    resetTtsPlayback(); 
    if (typeof stopVisualizer === 'function') {
        stopVisualizer();
    }
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
    else if (data.type === 'tts_barge_in') {
        console.log('[BARGE-IN] User interrupted, stopping TTS playback');
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
