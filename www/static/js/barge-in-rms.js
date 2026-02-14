class BargeInRmsDetector {
    constructor(options = {}) {
        this.baseThreshold = options.baseThreshold ?? 0.014;
        this.minFrames = options.minFrames ?? 2;
        this.cooldownMs = options.cooldownMs ?? 900;
        this.visMax = options.visMax ?? 0.05;
        this.noiseAlpha = options.noiseAlpha ?? 0.05;
        this.noiseMultiplier = options.noiseMultiplier ?? 2.8;
        this.minDynamicThreshold = options.minDynamicThreshold ?? 0.010;
        this.maxDynamicThreshold = options.maxDynamicThreshold ?? 0.035;
        this.initialAmbient = options.initialAmbient ?? 0.004;

        this.speechFrames = 0;
        this.lastTriggeredAt = 0;
        this.ambientRmsEma = this.initialAmbient;
        this.currentThreshold = this.baseThreshold;
    }

    _clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    _computeRmsFromInt16(int16Data) {
        if (!int16Data || int16Data.length === 0) return 0;
        let sumSquares = 0;
        for (let i = 0; i < int16Data.length; i++) {
            const normalized = int16Data[i] / 32768;
            sumSquares += normalized * normalized;
        }
        return Math.sqrt(sumSquares / int16Data.length);
    }

    _computeDynamicThreshold() {
        const adaptive = this.ambientRmsEma * this.noiseMultiplier;
        return this._clamp(
            Math.max(this.baseThreshold, adaptive),
            this.minDynamicThreshold,
            this.maxDynamicThreshold
        );
    }

    reset() {
        this.speechFrames = 0;
    }

    process(int16Data, isTtsSpeaking) {
        const rms = this._computeRmsFromInt16(int16Data);
        this.currentThreshold = this._computeDynamicThreshold();

        if (!isTtsSpeaking) {
            if (rms <= this.visMax) {
                this.ambientRmsEma = (1 - this.noiseAlpha) * this.ambientRmsEma + (this.noiseAlpha * rms);
                this.currentThreshold = this._computeDynamicThreshold();
            }
            this.speechFrames = 0;
            return {
                triggered: false,
                rms,
                threshold: this.currentThreshold,
                state: "silence",
                visMax: this.visMax
            };
        }

        let state = "silence";
        if (rms >= this.currentThreshold) {
            this.speechFrames += 1;
            state = this.speechFrames >= this.minFrames ? "trigger" : "near";
        } else {
            this.speechFrames = Math.max(0, this.speechFrames - 1);
            if (rms >= (this.currentThreshold * 0.7)) {
                state = "near";
            }
        }

        const nowMs = Date.now();
        let triggered = false;
        if (this.speechFrames >= this.minFrames && (nowMs - this.lastTriggeredAt) >= this.cooldownMs) {
            triggered = true;
            this.lastTriggeredAt = nowMs;
            this.speechFrames = 0;
        }

        return {
            triggered,
            rms,
            threshold: this.currentThreshold,
            state,
            visMax: this.visMax
        };
    }
}

window.BargeInRmsDetector = BargeInRmsDetector;
