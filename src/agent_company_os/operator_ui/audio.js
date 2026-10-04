/** Optional presentation audio. No runtime actions, network requests, or microphone at import. */
const SETTINGS_KEY = "agent-company-os.audio.v1";
const clamp = (value, low, high, fallback) => Number.isFinite(Number(value)) ? Math.min(high, Math.max(low, Number(value))) : fallback;
const safeStorage = env => { try { return env.localStorage; } catch { return null; } };
const readableError = error => String(error?.error || error?.message || error || "audio_unavailable");

export const AGENT_VOICE_PROFILES = Object.freeze({
  default: Object.freeze({ voice_id: null, speaking_rate: 1, pitch: 1, sonic_signature: "agent" }),
  research: Object.freeze({ voice_id: null, speaking_rate: 0.94, pitch: 1, sonic_signature: "agent" }),
  analytical: Object.freeze({ voice_id: null, speaking_rate: 0.98, pitch: 1, sonic_signature: "agent" }),
  writer: Object.freeze({ voice_id: null, speaking_rate: 1, pitch: 1.04, sonic_signature: "agent" }),
  engineering: Object.freeze({ voice_id: null, speaking_rate: 1.03, pitch: 0.98, sonic_signature: "agent" })
});

export function normalizeVoiceProfile(profile = {}) {
  return {
    voice_id: typeof profile.voice_id === "string" ? profile.voice_id : null,
    speaking_rate: clamp(profile.speaking_rate, 0.8, 1.2, 1),
    pitch: clamp(profile.pitch, 0.8, 1.2, 1),
    sonic_signature: typeof profile.sonic_signature === "string" ? profile.sonic_signature : "agent"
  };
}

/** SpeechInputPort: start(callbacks), stop(), cancel(), dispose(), supported. */
export class BrowserSpeechInputPort {
  constructor({ env = globalThis } = {}) {
    this.env = env;
    this.Recognition = env.SpeechRecognition || env.webkitSpeechRecognition;
    this.supported = Boolean(this.Recognition);
    this.session = null;
    this.disposed = false;
  }
  start({ lang = "en-US", onState = () => {}, onTranscript = () => {}, onError = () => {} } = {}) {
    if (this.disposed) throw new Error("audio_disposed");
    if (!this.supported) throw new Error("speech_input_unavailable");
    this.cancel();
    const recognition = new this.Recognition();
    const session = { recognition, onState, onError, failed: false };
    this.session = session;
    const current = () => this.session === session && !this.disposed;
    recognition.lang = lang;
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.onstart = () => { if (current()) onState("listening"); };
    recognition.onresult = event => {
      if (!current()) return;
      for (let i = event.resultIndex || 0; i < event.results.length; i++) {
        const result = event.results[i];
        const text = String(result[0]?.transcript || "");
        onTranscript({ text, final: Boolean(result.isFinal) });
        if (result.isFinal) onState("processing");
      }
    };
    recognition.onerror = event => {
      if (!current()) return;
      session.failed = true;
      const error = readableError(event);
      onError(error);
      onState(error === "aborted" ? "interrupted" : "error");
    };
    recognition.onend = () => {
      if (!current()) return;
      this.session = null;
      if (!session.failed) onState("idle");
    };
    onState("requesting_permission");
    try { recognition.start(); }
    catch (error) { this.session = null; onError(readableError(error)); onState("error"); }
  }
  stop() {
    if (!this.session) return;
    this.session.onState("processing");
    try { this.session.recognition.stop(); }
    catch (error) { this.session.onError(readableError(error)); this.session.onState("error"); this.cancel(); }
  }
  cancel() {
    const session = this.session;
    this.session = null;
    if (!session) return;
    // Detach handlers before aborting so late browser events cannot restart the UI.
    for (const name of ["onstart", "onresult", "onerror", "onend"]) session.recognition[name] = null;
    try { session.recognition.abort(); } catch { /* Already ended. */ }
    session.onState("interrupted");
  }
  dispose() { this.cancel(); this.disposed = true; }
}

/** SpeechOutputPort: speak(text, options) -> Promise<{status}>, cancel(), dispose(), supported. */
export class BrowserSpeechOutputPort {
  constructor({ env = globalThis } = {}) {
    this.env = env;
    this.synthesis = env.speechSynthesis;
    this.supported = Boolean(this.synthesis && env.SpeechSynthesisUtterance);
    this.session = null;
    this.disposed = false;
  }
  speak(text, { profile, volume = 0.5, lang = "en-US", onState = () => {}, onError = () => {} } = {}) {
    if (this.disposed) return Promise.resolve({ status: "disposed" });
    if (!this.supported) return Promise.resolve({ status: "unavailable", error: "speech_output_unavailable" });
    this.cancel();
    const voiceProfile = normalizeVoiceProfile(profile);
    return new Promise(resolve => {
      const utterance = new this.env.SpeechSynthesisUtterance(String(text));
      utterance.lang = lang;
      utterance.rate = voiceProfile.speaking_rate;
      utterance.pitch = voiceProfile.pitch;
      utterance.volume = clamp(volume, 0, 1, 0.5);
      try {
        const voices = this.synthesis.getVoices();
        const selected = voices.find(voice => voice.voiceURI === voiceProfile.voice_id || voice.name === voiceProfile.voice_id);
        if (selected) utterance.voice = selected;
      } catch { /* Device default voice is a valid fallback. */ }
      const session = { utterance, onState, finish: null };
      session.finish = result => {
        if (this.session !== session) return;
        this.session = null;
        utterance.onstart = utterance.onend = utterance.onerror = null;
        onState(result.status === "interrupted" ? "interrupted" : result.status === "error" ? "error" : "idle");
        resolve(result);
      };
      this.session = session;
      utterance.onstart = () => { if (this.session === session) onState("speaking"); };
      utterance.onend = () => session.finish({ status: "completed" });
      utterance.onerror = event => {
        if (this.session !== session) return;
        const error = readableError(event);
        if (["canceled", "interrupted"].includes(error)) session.finish({ status: "interrupted" });
        else { onError(error); session.finish({ status: "error", error }); }
      };
      onState("processing");
      try { this.synthesis.speak(utterance); }
      catch (error) { const message = readableError(error); onError(message); session.finish({ status: "error", error: message }); }
    });
  }
  cancel() {
    const session = this.session;
    if (!session) return;
    session.finish({ status: "interrupted" });
    try { this.synthesis.cancel(); } catch { /* Resolve our foreground session regardless. */ }
  }
  dispose() { this.cancel(); this.disposed = true; }
}

/** Deterministic fixture input: no timer, microphone, permissions, or browser dependency. */
export class MockSpeechInputPort {
  constructor() { this.supported = true; this.session = null; this.starts = 0; this.disposed = false; }
  start(callbacks = {}) {
    if (this.disposed) throw new Error("audio_disposed");
    this.cancel(); this.starts++; this.session = callbacks;
    callbacks.onState?.("requesting_permission"); callbacks.onState?.("listening");
  }
  emitTranscript(text, { final = true } = {}) {
    this.session?.onTranscript?.({ text: String(text), final });
    if (final) this.session?.onState?.("processing");
  }
  finish() { const session = this.session; this.session = null; session?.onState?.("idle"); }
  fail(error = "not-allowed") { this.session?.onError?.(error); this.session?.onState?.("error"); this.session = null; }
  stop() { this.finish(); }
  cancel() { const session = this.session; this.session = null; session?.onState?.("interrupted"); }
  dispose() { this.cancel(); this.disposed = true; }
}

/** Deterministic fixture output: call finish()/fail() to settle pending playback. */
export class MockSpeechOutputPort {
  constructor() { this.supported = true; this.session = null; this.calls = []; this.disposed = false; this.maxConcurrent = 0; }
  speak(text, options = {}) {
    if (this.disposed) return Promise.resolve({ status: "disposed" });
    this.cancel(); this.calls.push({ text: String(text), ...options });
    return new Promise(resolve => {
      this.session = { resolve, options };
      this.maxConcurrent = Math.max(this.maxConcurrent, Number(Boolean(this.session)));
      options.onState?.("speaking");
    });
  }
  finish() { const session = this.session; this.session = null; session?.options.onState?.("idle"); session?.resolve({ status: "completed" }); }
  fail(error = "speech_failed") { const session = this.session; this.session = null; session?.options.onError?.(error); session?.options.onState?.("error"); session?.resolve({ status: "error", error }); }
  cancel() { const session = this.session; this.session = null; session?.options.onState?.("interrupted"); session?.resolve({ status: "interrupted" }); }
  dispose() { this.cancel(); this.disposed = true; }
}

const CUES = Object.freeze({
  listening: { notes: [440, 620], duration: 0.085, priority: 20 },
  interaction: { notes: [560], duration: 0.055, priority: 1 },
  agent: { notes: [420, 540], duration: 0.08, priority: 5 },
  approval: { notes: [392, 523], duration: 0.12, priority: 30 },
  warning: { notes: [330, 294], duration: 0.12, priority: 40 },
  recovery: { notes: [196, 220], duration: 0.14, priority: 35 },
  unknown: { notes: [220, 233], duration: 0.14, priority: 35 }
});

export class AudioManager {
  constructor({ env = globalThis, inputPort, outputPort, storage, muted, volume, reducedMotion = false, enabled = true } = {}) {
    this.env = env;
    this.inputPort = inputPort || new BrowserSpeechInputPort({ env });
    this.outputPort = outputPort || new BrowserSpeechOutputPort({ env });
    this.storage = storage === undefined ? safeStorage(env) : storage;
    let settings = {};
    try { settings = JSON.parse(this.storage?.getItem(SETTINGS_KEY) || "{}"); } catch { /* Private mode or invalid settings. */ }
    settings = settings && typeof settings === "object" ? settings : {};
    this.enabled = Boolean(enabled);
    this.reducedMotion = Boolean(reducedMotion);
    this.listeners = new Set();
    this.context = null;
    this.foreground = null;
    this.activeCue = null;
    this.cueGeneration = 0;
    this.inputGeneration = 0;
    this.state = {
      muted: typeof muted === "boolean" ? muted : typeof settings.muted === "boolean" ? settings.muted : true,
      volume: clamp(volume ?? settings.volume, 0, 1, 0.45),
      speechState: "idle", inputState: "idle", outputState: "idle", foregroundAgentId: null,
      transcript: "", inputTranscript: "", error: null, disposed: false,
      supported: { input: Boolean(this.inputPort.supported), output: Boolean(this.outputPort.supported), cues: Boolean(env.AudioContext || env.webkitAudioContext) }
    };
  }
  getState() { return { ...this.state, supported: { ...this.state.supported } }; }
  subscribe(listener) {
    if (typeof listener !== "function") throw new TypeError("An audio listener must be a function");
    this.listeners.add(listener); listener(this.getState());
    return () => this.listeners.delete(listener);
  }
  _emit(patch = {}) {
    Object.assign(this.state, patch);
    this.state.speechState = ["requesting_permission", "listening", "processing", "error"].includes(this.state.inputState)
      ? this.state.inputState : this.state.outputState !== "idle" ? this.state.outputState : this.state.inputState;
    for (const listener of this.listeners) { try { listener(this.getState()); } catch { /* One view cannot break playback or other views. */ } }
  }
  _persist() { try { this.storage?.setItem(SETTINGS_KEY, JSON.stringify({ muted: this.state.muted, volume: this.state.volume })); } catch { /* Storage is optional. */ } }
  setMuted(muted) {
    if (this.state.disposed) return this.getState();
    if (muted) { this.stopSpeaking(); this._cancelCue(); }
    this._emit({ muted: Boolean(muted) }); this._persist(); return this.getState();
  }
  toggleMuted() { return this.setMuted(!this.state.muted); }
  setVolume(volume) {
    if (this.state.disposed) return this.getState();
    const level = clamp(volume, 0, 1, this.state.volume);
    if (level === 0) { this.stopSpeaking(); this._cancelCue(); }
    this._emit({ volume: level }); this._persist(); return this.getState();
  }
  async speak(text, { agentId = null, priority = 10, profile = {}, lang = "en-US" } = {}) {
    if (this.state.disposed) return { status: "disposed" };
    const transcript = String(text || "").trim();
    if (!transcript) return { status: "empty" };
    if (this.foreground && this.foreground.priority > Number(priority)) return { status: "suppressed" };
    this.stopSpeaking();
    this._emit({ transcript, error: null });
    if (!this.enabled) return { status: "disabled" };
    if (this.state.muted || this.state.volume === 0) return { status: "muted" };
    if (!this.outputPort.supported) { this._emit({ outputState: "error", error: "speech_output_unavailable" }); return { status: "unavailable" }; }
    this._cancelCue();
    // Listening is a separate operator action. Speaking never starts a microphone.
    if (["requesting_permission", "listening", "processing"].includes(this.state.inputState)) this.cancelListening();
    this._emit({ inputState: "idle" });
    const foreground = { agentId, priority: Number(priority) || 0 };
    this.foreground = foreground;
    this._emit({ foregroundAgentId: agentId, outputState: "processing" });
    const current = () => this.foreground === foreground && !this.state.disposed;
    let result;
    try {
      result = await this.outputPort.speak(transcript, {
        profile: normalizeVoiceProfile(profile), volume: this.state.volume, lang,
        onState: outputState => { if (current()) this._emit({ outputState }); },
        onError: error => { if (current()) this._emit({ error: readableError(error), outputState: "error" }); }
      });
    } catch (error) { result = { status: "error", error: readableError(error) }; }
    if (current()) {
      this.foreground = null;
      this._emit({ foregroundAgentId: null, outputState: result?.status === "error" || result?.status === "unavailable" ? "error" : result?.status === "interrupted" ? "interrupted" : "idle", error: result?.error || this.state.error });
    }
    return result || { status: "completed" };
  }
  stopSpeaking() {
    const active = Boolean(this.foreground);
    this.foreground = null;
    this.outputPort.cancel();
    if (active) this._emit({ outputState: "interrupted", foregroundAgentId: null });
  }
  startListening({ userGesture = false, lang = "en-US", onTranscript = () => {} } = {}) {
    if (this.state.disposed) return { status: "disposed" };
    if (!userGesture) return { status: "user_action_required" };
    if (!this.enabled) return { status: "disabled" };
    if (!this.inputPort.supported) { this._emit({ inputState: "error", error: "speech_input_unavailable" }); return { status: "unavailable" }; }
    this.stopSpeaking(); this._cancelCue(); this.cancelListening();
    const generation = ++this.inputGeneration;
    const current = () => generation === this.inputGeneration && !this.state.disposed;
    this._emit({ inputState: "requesting_permission", outputState: "idle", inputTranscript: "", error: null });
    try {
      this.inputPort.start({ lang,
        onState: inputState => { if (current()) this._emit({ inputState }); },
        onTranscript: transcript => {
          if (!current()) return;
          const value = { text: String(transcript.text || ""), final: Boolean(transcript.final) };
          this._emit({ inputTranscript: value.text }); onTranscript(value);
        },
        onError: error => { if (current()) this._emit({ inputState: "error", error: readableError(error) }); }
      });
    } catch (error) { this._emit({ inputState: "error", error: readableError(error) }); return { status: "error" }; }
    return { status: this.state.inputState };
  }
  stopListening() { this.inputPort.stop(); }
  cancelListening() {
    const active = ["requesting_permission", "listening", "processing"].includes(this.state.inputState);
    this.inputGeneration++; this.inputPort.cancel();
    if (active) this._emit({ inputState: "interrupted" });
  }
  interrupt() { this.stopSpeaking(); this.cancelListening(); this._cancelCue(); }
  resetSession() {
    if (this.state.disposed) return this.getState();
    this.interrupt();
    this._emit({ transcript: "", inputTranscript: "", error: null, foregroundAgentId: null, inputState: "idle", outputState: "idle" });
    return this.getState();
  }
  _cancelCue() {
    this.cueGeneration++;
    const cue = this.activeCue; this.activeCue = null;
    for (const node of cue?.nodes || []) { try { node.stop?.(); node.disconnect?.(); } catch { /* Cue already finished. */ } }
  }
  async cue(kind = "interaction", { userGesture = false, priority } = {}) {
    if (this.state.disposed) return { status: "disposed" };
    if (!this.enabled) return { status: "disabled" };
    if (this.state.muted || this.state.volume === 0) return { status: "muted" };
    if (this.foreground) return { status: "speech_foreground" };
    const definition = CUES[kind] || CUES.interaction;
    const rank = Number(priority ?? definition.priority);
    if (this.activeCue && this.activeCue.priority > rank) return { status: "suppressed" };
    if (!this.context && !userGesture) return { status: "user_action_required" };
    const Context = this.env.AudioContext || this.env.webkitAudioContext;
    if (!Context) return { status: "unavailable" };
    this._cancelCue();
    const token = this.cueGeneration;
    const cue = { priority: rank, nodes: [], token }; this.activeCue = cue;
    try {
      if (!this.context) this.context = new Context();
      if (this.context.state === "suspended") await this.context.resume();
      if (token !== this.cueGeneration || this.state.disposed || this.state.muted || this.foreground) return { status: "interrupted" };
      const gain = this.context.createGain(); cue.nodes.push(gain); gain.connect(this.context.destination);
      const now = this.context.currentTime;
      const duration = definition.duration * definition.notes.length;
      const peak = this.state.volume * (this.reducedMotion ? 0.035 : 0.055);
      gain.gain.setValueAtTime(0, now); gain.gain.linearRampToValueAtTime(peak, now + 0.015); gain.gain.linearRampToValueAtTime(0, now + duration);
      definition.notes.forEach((frequency, index) => {
        const oscillator = this.context.createOscillator(); cue.nodes.push(oscillator);
        oscillator.type = "sine"; oscillator.frequency.value = frequency; oscillator.connect(gain);
        oscillator.onended = () => {
          oscillator.disconnect();
          if (index === definition.notes.length - 1) { gain.disconnect(); if (this.activeCue === cue) this.activeCue = null; }
        };
        oscillator.start(now + index * definition.duration); oscillator.stop(now + (index + 1) * definition.duration);
      });
      return { status: "played" };
    } catch (error) { if (this.activeCue === cue) this._cancelCue(); this._emit({ error: readableError(error) }); return { status: "error" }; }
  }
  dispose() {
    if (this.state.disposed) return;
    this.interrupt(); this.inputPort.dispose?.(); this.outputPort.dispose?.();
    try { const closed = this.context?.close(); closed?.catch?.(() => {}); } catch { /* Browser already closed the context. */ }
    this.context = null; this._emit({ disposed: true, inputState: "idle", outputState: "idle", foregroundAgentId: null }); this.listeners.clear();
  }
}
