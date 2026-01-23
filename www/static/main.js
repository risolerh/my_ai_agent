let ws;
let audioContext;
let processor;
let stream;
let globalStream;

const statusEl = document.getElementById('status');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const logEl = document.getElementById('log');
const inputLangEl = document.getElementById('inputLang');
const outputLangEl = document.getElementById('outputLang');

let currentPartialEl = null;

// Load configuration on startup
window.addEventListener('DOMContentLoaded', async () => {
    try {
        // Fetch/Populate Input Models
        const modelsRes = await fetch('/api/models');
        const models = await modelsRes.json();
        models.forEach(m => {
            // Only show downloaded models
            if (!m.downloaded) return;

            const opt = document.createElement('option');
            opt.value = m.id;
            opt.textContent = m.lang;

            if (m.id === '2') opt.selected = true; // Default to English Complete (ID 2)
            inputLangEl.appendChild(opt);
        });

        // Fetch/Populate Output Languages
        const langsRes = await fetch('/api/languages');
        const langs = await langsRes.json();
        langs.forEach(l => {
            const opt = document.createElement('option');
            opt.value = l.code;
            opt.textContent = l.name;
            if (l.code === 'es') opt.selected = true;
            outputLangEl.appendChild(opt);
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

async function startStream() {
    try {
        // Initialize WebSocket with selected languages
        const inputLang = inputLangEl.value;
        const outputLang = outputLangEl.value;
        const url = `ws://${window.location.host}/ws/stream?input_lang=${inputLang}&output_lang=${outputLang}`;

        console.log("Connecting to", url);
        ws = new WebSocket(url);
        ws.binaryType = 'arraybuffer';

        ws.onopen = () => {
            setStatus('Connected', '#aaffaa');
            startAudio();
        };

        ws.onclose = () => {
            setStatus('Disconnected', '#ffaaaa');
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

        startBtn.disabled = true;
        stopBtn.disabled = false;
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
    if (ws) {
        ws.close();
    }
    startBtn.disabled = false;
    stopBtn.disabled = true;
    setStatus('Stopped', '#eee');
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
