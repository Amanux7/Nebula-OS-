# Spatial command center

The command center is served at `/command` by the existing loopback operator host.
The established inspection console remains at `/`. Both use the same authenticated,
workspace-scoped Stage 11 read APIs. The Aurora Desk seed is synthetic canonical
data; its age and historical states are visible rather than presented as live work.

## Implementation storyboard

| Screen | Hierarchy and interaction | Spatial / motion behavior | Audio | Required backend data |
| --- | --- | --- | --- | --- |
| Command Core | Company identity, current mode, agent presence, attention items, command input | Restrained wire lattice with state text; scene pauses offscreen | Off by default; explicit listening or reading only | status, workspaces, agents, runs, goals, tasks, approvals |
| Organization | Company → department → agent; select department or identity | Bounded perspective, zoom, tilt, reset, persistent focus; list on narrow screens | Optional selection cue | departments, agents, organization / versions, canonical memberships |
| Agent Conversation | Selected identity, latest recorded run, safe metadata transcript, input and playback controls | Foreground identity with a continuous speech trace | Generic configurable TTS; explicit microphone; interruption | agents, runs, tasks, messages; no model conversation endpoint exists |
| Goal / Execution Stack | Goal selector, progress by actual states, task dependencies, lineage layers | Independently scrolling Goal → Plan → Task → Run → Intent → Invocation → Receipt stack; readable details outside transforms | Optional focus cue | goals, tasks, lineage, plans, materializations, runs, intents, invocations, receipts |
| Company Brain | Sources and versions linked to recorded evidence; separate memory trail | Structured lattice; animate only on actual new retrieved events, never synthetic pulses | Read metadata only | knowledge, knowledge_versions, memory, runs pack references, audit |
| Approval | Requested operation, actor/tool, policy, digest, expiry and decisions | Warm static focus; disabled decision controls | Optional explicit non-alarming cue | approvals, intents, approval_requests, approval_decisions |
| Recovery | Uncertainty distinguished from failure; classification, evidence and links | Slower asymmetric core state, no flashing; quarantine always above navigation | Optional explicit low cue | recovery, status, restore |
| Audit | Goal selector, ordered committed events, correlations, metadata and record links | Ordered vertical trace; keyboard accessible | Silent unless explicitly read | audit/goals, lineage, messages, handoffs |

## State and authority

The data port owns canonical read projections and bounded page cursors. View selection,
scene quality, entity focus, layer position and dialogs are derived UI state. The core
presentation derives only from loaded run/status/attention records and speech state.
Voice state belongs to AudioManager. Neither audio profiles nor scene nodes grant
authority. Approval/retry/release controls are absent or disabled on this surface.

Text commands route to local read contexts or explain available metadata. They do
not invoke models, tools, shell commands, permission changes, or autonomous work.
Speech recognition may depend on the browser/provider; the microphone notice names
that boundary. The visible transcript remains usable when audio is unsupported.

## Accessibility and graceful degradation

Named buttons, headings, keyboard focus rings, skip navigation, native dialogs with
focus restoration, status text and labelled states accompany visual glyphs. Escape
closes the palette/details. Ctrl/Cmd+K opens the palette. Reduced motion presents
static geometry and a 2D stack; an explicit motion toggle is available. WebGL is not
required: the core uses bounded Canvas2D projection with a static labelled fallback.
Mobile uses sequential agent/department lists and retains goals, conversation,
approvals and recovery. No runtime information depends on sound or animation.

## Scope and diagnostics

No backend authority or redaction expansion. Missing memberships/evidence detail
are explicitly reported as unavailable from the current read contract. API failures,
expired sessions, unsupported speech and empty categories have named states. Polling
is bounded and visible; partial pages are labelled. Development diagnostics record
load duration, API latency, core frame drops and speech initialization locally only.

The deterministic demo is operator-directed: Command → Organization → Agent → Goal
stack → Brain → Tools → Approvals → Recovery → Audit. Transitions visualize loaded
canonical records; they never manufacture activity or knowledge retrieval.
