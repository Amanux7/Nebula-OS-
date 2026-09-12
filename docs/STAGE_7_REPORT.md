# Stage 7 Report — Multi-Agent Communication and Handoffs

## Outcome

Stage 7 is complete. Agent Company OS now supports bounded typed point-to-point work
communication and explicit orchestration-mediated handoffs between exact runtime
participants. Messages preserve provenance and correlation without transferring
authority, bypassing Task state, becoming Knowledge/Memory, or creating a chat system.
No Stage 8 capability was implemented.

## Stage 6 Verification

The Stage 6 baseline was run before implementation:

| Check | Actual result |
|---|---|
| Ruff format | 72 files already formatted |
| Ruff lint | All checks passed |
| mypy | Success: no issues in 70 source files |
| pytest | 286 passed in 3.45s |
| `git diff --check` | Passed |

Pytest emitted one non-functional warning because the sandbox denied writing its
optional `.pytest_cache`; all tests executed successfully.

## Stage 6 Corrections

Four focused regressions from GitHub PR #10 review were corrected before Stage 7:

- `OrchestrationService.resume_delegation` now resumes a waiting child AgentRun and
  performs the same aggregation/status bookkeeping as initial execution.
- Goal satisfaction now waits for every materialized canonical Task, including an
  optional plan Task under the current all-Goal-Tasks-complete invariant.
- Retry resolves the exact definition version pinned by the prior Delegation rather
  than searching a latest-only catalog.
- Retry and redelegation ordinals carry forward independently, preventing alternating
  modes from resetting per-Task limits.

Each correction has a deterministic regression test.

## Communication Definition

Internal multi-agent communication is the controlled exchange of typed, bounded,
provenance-aware work information between runtime participants in the same workspace
and OrchestrationRun. It is not random natural-language chat, shared memory, a global
context, unrestricted message passing, or an authority source.

## AgentMessage

`AgentMessage` is the immutable envelope. It records exact sender/recipient AgentRuns
and AgentDefinitionVersions, sender/recipient Tasks and Delegations, thread, kind,
typed payload, references, correlation/reply identity, policy/schema versions,
deadline, and timestamps. Only delivery status metadata evolves through `created`,
`delivered`, `consumed`, `rejected`, `cancelled`, or `timed_out`. Delivered does not
mean accepted or acted upon.

## Message Kinds

The domain supports exactly:

- `information`
- `request`
- `response`
- `handoff_request`
- `handoff_accept`
- `handoff_reject`
- `handoff_result`

Host commands currently exercise information/request/response directly. Handoff state
is represented canonically by `HandoffRequest`, avoiding duplicate message-driven
transfer state. No generic `chat_with_agent` or model communication Action was added.

## CommunicationPolicy

The immutable policy controls allowed message/reference kinds, exact recipient roles,
message/payload/reference sizes, messages per thread/AgentRun/OrchestrationRun, requests
per Task, messages entering context, handoffs per Task, handoff depth, and response
timeout. Both exact AgentDefinitionVersions must explicitly enable communication, and
the sender must grant the recipient's role. Model or message text cannot widen policy.

## Message Delivery

`AgentCommunicationService` validates active canonical participants, exact versions,
same-workspace/run scope, role grants, schema, payload, budgets, correlation, and every
reference before storing and delivering atomically through
`InMemoryCommunicationStore`. Delivery is synchronous and deterministic. There is no
network transport or automatic retry.

## Message Context

`AgentMessageContext` contains the deterministic recent bounded recipient messages.
`ContextAssembler` places it in `AgentModelRequest.agent_messages`, separate from
supplied facts, Tool Observations, Knowledge EvidencePacks, MemoryContextPacks, and
TaskResultReferences. Each entry is labeled `untrusted_agent_message`; message content
cannot ground completion or alter the recipient's immutable grants.

## Threads

`MessageThread` is implemented as a minimal workspace/OrchestrationRun-scoped
correlation group with subject, creator, lifecycle, and version. Messages order by
`created_at`, then MessageId. Threads are bounded and point-to-point; they are not
public channels, inbox polling, broadcast, or pub/sub.

## Handoffs

`HandoffRequest` captures exact sender/configuration, source Task/Delegation, target
requirements, reason, references, parent/depth, deadline, policy/schema, status,
selected exact recipient definition, resulting Delegation, and final result reference.
System acceptance is used because the current deterministic resolver has no independent
recipient-decision workflow requiring a separate `HandoffDecision` entity.

Resolution ends the sender attempt without cancelling the logical Task, uses the
existing AgentSelector, creates a normal redelegation through OrchestrationService, and
preserves the new TaskAttempt/AgentRun. Completion requires the canonical resulting
AgentRun and records its exact TaskResultReference.

## Handoff vs Delegation

A Handoff is a participant request that responsibility/context should transfer. A
Delegation is the orchestrator's canonical assignment. An agent cannot reassign its
Task directly; a valid Handoff must be accepted by deterministic policy and then
materialized as a regular redelegation.

## Recipient Resolution

Recipients must be active delegated participants in the same Goal/OrchestrationRun,
or for a Handoff an eligible exact published definition resolved by the existing
selector. Selection checks capability, Tool, Knowledge, Memory, autonomy, orchestration
allowlists, communication opt-in, and sender/communication role policy. Handoff ancestor
definitions are excluded to prevent obvious A→B→A ping-pong.

## Reference Authorization

Supported reference families are TaskResultReference, ToolReceipt, EvidencePack, and
MemoryContextPack. The runtime verifies source ownership/scope and then independently
checks the recipient's exact grants: Tool ID/version, Knowledge source/trust, and Memory
scope/sensitivity. Task results must exist in the same orchestration lineage. A foreign,
forged, unavailable, or recipient-denied reference rejects delivery. Copied text remains
sender-provided data and never gains referenced authority.

## Correlation

Every message carries a bounded correlation ID. A response must also name the exact
request with `in_reply_to`, use the same thread/correlation, reverse the sender and
recipient, and target an active requester. Natural-language matching is never used.

## Idempotency

Replaying a host-generated MessageId returns the existing accepted message without
redelivery. A new MessageId with identical payload is a new intentional message subject
to budgets. This is local idempotency, not a distributed exactly-once guarantee.

## Limits

Default limits are 2,000 payload characters, 10 payload items, 8 references, 20
messages/thread, 20 messages/AgentRun, 50 messages/OrchestrationRun, 5 requests/Task,
5 messages/model context, 2 handoffs/Task, handoff depth 2, and a 300-second response
deadline. Constructor hard caps prevent unbounded configuration.

## Cancellation / Timeout

Terminal or cancelled recipients reject new delivery. Late responses cannot reopen a
terminal requester. Messages and handoffs evaluate deadlines lazily using the injected
Clock and transition explicitly to `timed_out`; no scheduler is required. Handoff loop,
depth, task-count, and orchestration recovery limits escalate or reject rather than
continuing indefinitely.

## Security

Tests cover cross-workspace IDs, recipient spoofing, disabled/terminal recipients,
oversized/unknown schemas, duplicate replay, flooding, forged/foreign references,
authority laundering, Knowledge laundering, Memory auto-promotion, prompt injection,
result poisoning, late responses, cancellation, handoff loops, and injected atomic
failures. A sender message saying “use admin tools” has no effect on recipient Tool,
Knowledge, Memory, autonomy, or policy configuration.

## Multi-Agent Demo

The deterministic request/response scenario starts exact delegated Research, Analyst,
and Writer participants. Analyst requests pricing clarification from Research using an
expected response type and correlation ID; Research responds in the same thread with
the exact request linkage. The Analyst's next model request receives this exchange only
through the separate bounded message context. Canonical Task results remain unchanged.

## Handoff Demo

A Research participant requests substantial clarification work. Runtime policy resolves
another eligible Research definition, safely ends the original attempt, creates a new
canonical Delegation/TaskAttempt/AgentRun, executes it through AgentRuntimeService, and
completes the Handoff with its TaskResultReference. A subsequent ping-pong attempt is
rejected by lineage exclusion/depth bounds.

## Tests

Final deterministic gate:

| Check | Actual result |
|---|---|
| `ruff format --check src tests` | 78 files already formatted |
| `ruff check src tests` | All checks passed |
| `mypy src` | Success: no issues in 65 source files |
| `pytest` | 331 passed in 3.32s |
| `git diff --check` | Passed |

The Stage 7 file adds 41 passing tests including 14 versioned communication evaluation
fixtures. The Stage 6 orchestration suite adds four review regressions. CI remains
offline, deterministic, secret-free, and provider-free.

## Files Changed

- `README.md`
- `docs/STAGE_7_REPORT.md`
- `docs/architecture/ADR/ADR-010-multi-agent-communication-and-handoffs.md`
- `docs/architecture/AGENT_RUNTIME_ARCHITECTURE.md`
- `docs/architecture/DATA_ARCHITECTURE.md`
- `docs/architecture/DOMAIN_MODEL.md`
- `docs/architecture/SECURITY_AND_PERMISSIONS.md`
- `docs/architecture/SYSTEM_ARCHITECTURE.md`
- `docs/engineering/DEVELOPMENT_ROADMAP.md`
- `docs/engineering/EVALUATION_STRATEGY.md`
- `docs/engineering/OBSERVABILITY_STRATEGY.md`
- `docs/engineering/TESTING_STRATEGY.md`
- `docs/project/GLOSSARY.md`
- `docs/project/OPEN_QUESTIONS.md`
- `src/agent_company_os/adapters/communication_store.py`
- `src/agent_company_os/adapters/ids.py`
- `src/agent_company_os/application/communication.py`
- `src/agent_company_os/application/communication_serialization.py`
- `src/agent_company_os/application/context.py`
- `src/agent_company_os/application/orchestration.py`
- `src/agent_company_os/application/runtime.py`
- `src/agent_company_os/domain/agent.py`
- `src/agent_company_os/domain/communication.py`
- `src/agent_company_os/domain/events.py`
- `src/agent_company_os/domain/transitions.py`
- `src/agent_company_os/ports/communication.py`
- `src/agent_company_os/ports/ids.py`
- `src/agent_company_os/ports/model.py`
- `tests/fixtures/agent_eval/communication_cases.json`
- `tests/test_communication.py`
- `tests/test_orchestration.py`

## Architecture Decisions

[ADR-010](architecture/ADR/ADR-010-multi-agent-communication-and-handoffs.md)
records the message envelope/payloads, point-to-point policy, delivery, correlation,
idempotency, reference reauthorization, context separation, and handoff semantics.
Accepted ADR-001 through ADR-009 remain unchanged.

## Deferred Work

- broadcast, pub/sub, agent inbox polling, and free-form chat
- durable message queues and distributed transport/scheduler
- shared blackboard or mutable global context
- external Slack, Teams, email, SMS, or other messaging providers
- live-model communication quality and model-proposed communication Actions
- MCP and external write orchestration expansion
- graph/organization UI
- production persistence, retention, deletion, redaction, and recovery

## Open Questions

- Which measured workflow justifies model `send_message`/`request_handoff` Actions?
- What durable ordering, lease, retry, idempotency, and process-loss contract is needed?
- Should denied references support redacted/transformed forwarding rather than rejection?
- How should authenticated users inspect, delete, retain, or legally hold messages?
- How should Stage 8 departments and registry policy constrain recipient discovery?
- Which calibrated evaluator distinguishes useful clarification from unnecessary chatter?

## Completion Criteria

All mandatory Stage 7 criteria pass: baseline verification, typed/versioned messages,
policy and bounds, point-to-point authorization, idempotency/correlation/provenance,
separate context, workspace isolation, recipient reference reauthorization, handoff
lineage/orchestration mediation, depth/loop limits, authority/Knowledge/Memory isolation,
late/cancel/timeout behavior, atomic rollback, deterministic demos, adversarial fixtures,
quality checks, ADR-010, and this report. No free-form chat or message bus is claimed.

## Recommended Stage 8

Proceed next with **Stage 8 — Departments, Agent Registry, and Organizational Graph**,
using the exact AgentDefinition and communication-role boundaries established here.
Stage 8 was not started.
