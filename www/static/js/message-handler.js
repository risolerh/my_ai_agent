/**
 * WebSocket message handler.
 * Processes all incoming messages from the server and updates the UI.
 *
 * Dependencies (globals from main.js loaded before this script):
 *   DOM elements : logEl, voiceEnabledEl
 *   State        : currentPartialEl (read/write), ttsVoices, currentInputLangCode
 *   Functions    : setButtonsState, setStatus, updateVoiceOptions,
 *                  normalizeVoices, resetTtsPlayback, playTtsChunk
 */

let lastFinalSignature = '';
let lastFinalAtMs = 0;
const FINAL_DEDUP_WINDOW_MS = 2500;

function currentTimestamp() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, '0');
    const mm = String(now.getMinutes()).padStart(2, '0');
    const ss = String(now.getSeconds()).padStart(2, '0');
    return `${hh}:${mm}:${ss}`;
}

function resetMessageHistoryState() {
    lastFinalSignature = '';
    lastFinalAtMs = 0;
    const streamEl = document.getElementById('agent-streaming');
    if (streamEl) {
        streamEl.remove();
    }
}

function handleMessage(data) {
    // ── Partial transcription (live typing) ──────────────────────────
    if (data.type === 'partial') {
        const text = (data.original || '').trim();
        if (!text) return;

        // Keep UI stable: ignore duplicate/regressive partials that cause trailing-word blink
        const lastPartial = currentPartialEl?.dataset?.lastText || '';
        if (text === lastPartial) return;
        if (lastPartial && lastPartial.startsWith(text)) return;

        if (!currentPartialEl) {
            currentPartialEl = document.createElement('div');
            currentPartialEl.className = 'partial';
            currentPartialEl.dataset.timestamp = currentTimestamp();
            logEl.appendChild(currentPartialEl);
        }
        currentPartialEl.dataset.lastText = text;
        const partialTs = currentPartialEl.dataset.timestamp || currentTimestamp();
        currentPartialEl.innerHTML = `<span class="entry-time">[${partialTs}]</span> >> ${text}`;
        logEl.scrollTop = logEl.scrollHeight;
    }

    // ── Final transcription + translation ────────────────────────────
    else if (data.type === 'final') {
        if (currentPartialEl) {
            currentPartialEl.remove();
            currentPartialEl = null;
        }

        const originalText = (data.original || '').trim();
        if (!originalText) return;

        const inLang = data.input_lang || 'SRC';
        const outLang = data.output_lang || 'TGT';
        const signature = `${inLang}|${outLang}|${originalText.toLowerCase()}`;
        const now = Date.now();
        if (signature === lastFinalSignature && (now - lastFinalAtMs) < FINAL_DEDUP_WINDOW_MS) {
            return;
        }
        lastFinalSignature = signature;
        lastFinalAtMs = now;

        const container = document.createElement('div');
        const entryTs = currentTimestamp();

        container.innerHTML = `
            <div class="final"><span class="entry-time">[${entryTs}]</span> <b>[${inLang.toUpperCase()}]</b> ${originalText} <span style="font-size:0.8em;color:#aaa">(${data.confidence.toFixed(2)})</span></div>
            <div class="translation"><span class="entry-time">[${entryTs}]</span> <b>[${outLang.toUpperCase()}]</b> ${data.translation}</div>
            <hr/>
        `;
        logEl.appendChild(container);
        logEl.scrollTop = logEl.scrollHeight;
    }

    // ── WebSocket ready ──────────────────────────────────────────────
    else if (data.type === 'ready') {
        setButtonsState('streaming');
        if (data.input_lang) {
            currentInputLangCode = data.input_lang;
            updateVoiceOptions();
        }
        setStatus('Conectado', '#aaffaa');
    }

    // ── TTS voices list ──────────────────────────────────────────────
    else if (data.type === 'tts_voices') {
        ttsVoices = normalizeVoices(data.voices || []);
        updateVoiceOptions();
    }

    // ── TTS audio chunk ──────────────────────────────────────────────
    else if (data.type === 'tts_audio') {
        if (data.data) {
            playTtsChunk(data.data, data.sample_rate, {
                segment: data.segment,
                text: data.text || ''
            }).catch(() => { });
        }
    }

    // ── TTS error ────────────────────────────────────────────────────
    else if (data.type === 'tts_error') {
        const container = document.createElement('div');
        const errorText = data.error || "TTS error";
        const entryTs = currentTimestamp();
        container.innerHTML = `
            <div class="agent agent-error"><span class="entry-time">[${entryTs}]</span> <b>[TTS]</b> ${errorText}</div>
            <hr/>
        `;
        logEl.appendChild(container);
        logEl.scrollTop = logEl.scrollHeight;
    }

    // ── TTS interrupted ──────────────────────────────────────────────
    else if (data.type === 'tts_interrupted') {
        resetTtsPlayback();
    }

    // ── TTS barge-in ─────────────────────────────────────────────────
    else if (data.type === 'tts_barge_in') {
        console.log('[BARGE-IN] User interrupted, stopping TTS playback');
        resetTtsPlayback();
    }

    // ── Session conversation history cleared ──────────────────────────
    else if (data.type === 'conversation_cleared') {
        resetMessageHistoryState();
        setStatus('Conversation cleared', '#e6f7ff');
    }

    // ── Agent streaming chunks (live LLM output) ─────────────────────
    else if (data.type === 'agent_chunk') {
        if (data.status === 'start') {
            const container = document.createElement('div');
            container.id = 'agent-streaming';
            container.className = 'agent agent-streaming';
            const entryTs = currentTimestamp();
            container.innerHTML = `<span class="entry-time">[${entryTs}]</span> <b>[AGENT • ${data.model || ''}]</b> <span class="agent-stream-text"></span><span class="agent-cursor">▊</span>`;
            logEl.appendChild(container);
            logEl.scrollTop = logEl.scrollHeight;
        } else if (data.status === 'streaming') {
            const streamEl = document.getElementById('agent-streaming');
            if (streamEl) {
                const textSpan = streamEl.querySelector('.agent-stream-text');
                if (textSpan) {
                    textSpan.textContent += data.chunk;
                }
                logEl.scrollTop = logEl.scrollHeight;
            }
        } else if (data.status === 'done') {
            const streamEl = document.getElementById('agent-streaming');
            if (streamEl) streamEl.remove();
        } else if (data.status === 'cancelled') {
            const streamEl = document.getElementById('agent-streaming');
            if (streamEl) {
                const cursor = streamEl.querySelector('.agent-cursor');
                if (cursor) cursor.remove();
                streamEl.classList.remove('agent-streaming');
                streamEl.classList.add('agent-cancelled');
                const textSpan = streamEl.querySelector('.agent-stream-text');
                if (textSpan) {
                    textSpan.textContent += ' [cancelled]';
                }
                streamEl.removeAttribute('id');
                const hr = document.createElement('hr');
                streamEl.parentNode.insertBefore(hr, streamEl.nextSibling);
            }
        }
    }

    // ── Agent final response ─────────────────────────────────────────
    else if (data.type === 'agent') {
        const streamEl = document.getElementById('agent-streaming');
        if (streamEl) streamEl.remove();

        const container = document.createElement('div');
        const entryTs = currentTimestamp();
        if (data.status === 'ok') {
            container.innerHTML = `
                <div class="agent"><span class="entry-time">[${entryTs}]</span> <b>[AGENT • ${data.model}]</b> ${data.response}</div>
                <hr/>
            `;
            if (voiceEnabledEl.checked) {
                resetTtsPlayback();
            }
        } else {
            const errorText = data.error || "Agent error";
            container.innerHTML = `
                <div class="agent agent-error"><span class="entry-time">[${entryTs}]</span> <b>[AGENT • ${data.model}]</b> ${errorText}</div>
                <hr/>
            `;
        }
        logEl.appendChild(container);
        logEl.scrollTop = logEl.scrollHeight;
    }
}
