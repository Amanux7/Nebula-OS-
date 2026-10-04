# Presentation audio system

Audio adds a quiet identity to Agent Company OS while canonical state remains visible in text. The centralized `AudioManager` owns preference, volume, foreground speech, cue arbitration, browser resource cleanup, and state notifications. It never calls a runtime API, authorizes an action, retrieves hidden reasoning, or constructs an Agent response.

## Identity and cue language

`AGENT_VOICE_PROFILES` offers restrained generic profiles: default, research, analytical, writer, and engineering. Profile configuration uses a device `voice_id`, `speaking_rate`, constrained `pitch`, and `sonic_signature`. Rate and pitch stay between 0.8 and 1.2. An unavailable voice falls back to the device default. Voice identity conveys presentation only; it has no relationship to principal, department membership, autonomy, Tool permissions, or AgentRun identity. No character impersonation or copyrighted voice is hardwired.

Short synthesized sine cues cover activation, interaction, agent presence, approval, warning, recovery, and unknown outcome. Approval rises gently; uncertainty uses a low close interval rather than an alarm. Durations range from 55 ms for an interaction to 280 ms for a recovery cue. Their low gain limits interruption. Sound cannot replace the persistent visual approval/recovery indication. Reduced-motion presentation also lowers cue intensity; operators can mute all sound independently.

## Safe defaults and preferences

The initial preference is muted with volume 0.45. Importing or constructing a manager creates no microphone session, speech utterance, or AudioContext. Output starts only when the host requests playback after the operator enables sound. AudioContext construction additionally requires an explicitly initiated first cue (`userGesture: true`). Later cues reuse that context.

Mute stops speech and active cues immediately. Volume zero also cancels playback. Other volume changes apply to the next utterance, since browser synthesis does not consistently change an utterance already in progress. Mute controls output; the explicit microphone control remains independently available. The host must communicate listening clearly even while sound is off.

Only `{ muted, volume }` is persisted in guarded localStorage under `agent-company-os.audio.v1`. Storage denial, malformed values, and private browsing degrade to in-memory preferences. Transcripts, Agent IDs, and canonical data are never stored by this layer.

## Ports and controller contract

`SpeechInputPort` exposes `supported`, `start(callbacks)`, `stop()`, `cancel()`, and `dispose()`. Input callbacks publish `onState`, `onTranscript({ text, final })`, and `onError`. `SpeechOutputPort` exposes `supported`, `speak(text, options)` returning a settlement Promise, `cancel()`, and `dispose()`.

Initial browser ports use Web Speech recognition and synthesis. Ports can later be replaced without changing the controller. Browser recognition may use the browser vendor's remote recognition service; this implementation does not promise local-only speech processing. The interface should disclose browser speech before first microphone use and preserve typed input as a complete alternative. No raw audio stream or permanent recording is acquired.

```js
import { AudioManager } from "./audio.js";
const audio = new AudioManager();
const unsubscribe = audio.subscribe(state => {
  soundButton.textContent = state.muted ? "Sound off" : "Sound on";
  transcript.textContent = state.transcript;
  voiceState.textContent = state.speechState.replaceAll("_", " ");
});
soundButton.addEventListener("click", () => audio.toggleMuted());
readbackButton.addEventListener("click", () => {
  audio.speak(selectedCanonicalSummary, { agentId: selectedAgentId, priority: 20 });
});
stopButton.addEventListener("click", () => audio.stopSpeaking());
// On sign out, context change, or view teardown:
unsubscribe();
audio.dispose();
```

`getState()` returns a copy containing mute/volume, input and output state, derived speech state, current foreground Agent ID, transcript, input transcript, supported capabilities, error, and disposed status. Browser callbacks use ownership/generation guards so a stale canceled response cannot move a newer voice session out of focus.

## Arbitration and lifecycle

Only one foreground utterance exists. A new request of equal or greater priority interrupts the prior utterance. A lower-priority request is suppressed rather than queued behind information that may become stale. `stopSpeaking()` settles cancellation even if the browser fails to emit an end event. Explicit microphone activation interrupts TTS, and TTS cancels an active listening session to prevent self-transcription.

Only one cue is active. Higher or equal priority replaces the prior cue; lower priority is suppressed. Foreground TTS suppresses all cues. Priorities communicate presentation precedence, never backend authority. `dispose()` aborts recognition, stops synthesis/cues, closes the owned AudioContext, releases listeners, and prevents new capture/playback.

## Deterministic verification

`MockSpeechInputPort` and `MockSpeechOutputPort` use explicit `emitTranscript`, `finish`, and `fail` methods without timers, sound, or permission dialogs. `AudioManager({ enabled: false })` preserves text and disables all input/output activation. Run:

```powershell
node tests/fixtures/audio_contract.mjs
```

The dependency-free contract covers silent construction, preferences/storage failure, transcript availability, mute/zero volume, concurrent requests and stale cancellation, explicit microphone gating, denied permission, untrusted transcript handling, browser state transitions, generic voice selection, cue priority, unsupported browser fallback, and teardown. The test imports the browser ESM module via a data URL, so the Python project's lack of a JavaScript package manifest does not change module interpretation.
