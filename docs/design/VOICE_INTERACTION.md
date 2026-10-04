# Voice interaction and operator control

Voice is an optional way to navigate and inspect the same canonical company state shown in the interface. It does not create an AgentRun, execute a Tool, accept a plan, approve an ActionIntent, release quarantine, or alter authorization. A selected Agent's voice is a presentation profile rather than a new principal.

## Interaction storyboard

The Agent conversation view begins with Agent identity, current Task, autonomy label, readable canonical summary, and an idle core. A text command field remains available. The operator explicitly chooses the microphone control; only then can the browser request permission. The control and nearby status identify `requesting permission` followed by `listening`. Input transcript appears as plain text while the browser recognizes speech. Final input becomes `processing` briefly, then returns to idle when recognition ends.

A bounded local navigation interpreter can route inspection requests such as “Show approvals,” “Open organization,” or “Show recovery.” Unknown commands should receive a clear explanation and keep the transcript available for editing. Imperative phrases that request new runtime action are not fulfilled by the read-only command center. Final transcription is user input and must never be inserted through `innerHTML`, evaluated, or treated as policy.

Readback is explicit. The operator can choose to hear the selected canonical summary, enabling sound first if it is muted. While speaking, the selected Agent remains in focus and the exact spoken text remains visible. `Stop speaking` interrupts output immediately. Choosing the microphone while speaking stops playback before capture begins. Return to the command core stops any active voice session; sign-out resets speech state and clears both transcripts. Page teardown disposes the manager.

No generated dialogue, simulated Agent thought, or fake microphone activity is introduced. Until a backend conversation provider exists, the experience supports local inspection/navigation and readback of available canonical text. The host should describe these capabilities accurately.

## Speech states

| State | Visible behavior | Available operator action |
| --- | --- | --- |
| idle | Neutral voice indicator; no listening claim | Type, start microphone, request readback |
| requesting_permission | Explicit browser permission message | Cancel and continue typing |
| listening | Persistent microphone-active label | Stop listening or cancel |
| processing | Final transcript remains readable | Cancel or edit text |
| speaking | Text readback and selected Agent identity | Stop speaking, mute, start microphone |
| interrupted | Playback/capture stopped; transcript retained | Retry explicitly or type |
| error | Specific speech/permission error and text alternative | Retry explicitly or continue typing |

The `speechState` derives from separate input/output states. Canonical task/run statuses stay separate. A listening animation must not make an idle AgentRun appear active. Native SpeechRecognition provides no audio amplitude; the initial orbital/pulse visualization can react to reported speech state or transcript events, but should not claim to be a measured waveform. A future audio-analysis port may supply real amplitude without changing authorization boundaries.

## Integration

```js
microphoneButton.addEventListener("click", () => {
  audio.startListening({
    userGesture: true,
    onTranscript: ({ text, final }) => {
      commandInput.value = text;
      if (final) routeReadOnlyNavigation(text);
    }
  });
});
stopListeningButton.addEventListener("click", () => audio.stopListening());
cancelVoiceButton.addEventListener("click", () => audio.interrupt());
```

The `userGesture` flag is a UI contract guarding accidental initialization, not a security permission. Call it from an explicit button or keyboard handler. Browser permission remains authoritative. No `getUserMedia` call, always-on listener, automatic retry, or background capture occurs. Speech recognition commonly requires browser support and a secure context or localhost. Unsupported browsers keep the text command surface usable.

## Accessibility, privacy, and errors

All controls require visible labels, semantic buttons, accessible names, focus indicators, and keyboard access. Voice state belongs in a polite status region; avoid announcing every interim token. Readback transcript is mandatory and remains available when muted, unsupported, or interrupted. Status, approval, uncertainty, and recovery remain understandable without audio or animation. Reduced motion can replace a pulsing core with a stable state indicator.

Browser speech recognition can involve the browser vendor's service. Explain that before first activation; permission is requested only after the operator's action. Keep “microphone unavailable,” “permission denied,” and “speech unavailable” distinct from runtime failure. Network recognition errors should stop listening and invite a deliberate retry; the system must never silently reopen a microphone. This layer does not persist transcript history or retain raw audio.

Agent readback repeats visible canonical facts. It never claims a Tool succeeded merely because an utterance completed. Unknown external outcome remains uncertain in both the text and spoken explanation, and automatic retry remains governed by the backend. Restore quarantine is always visible even while a voice view is focused.
