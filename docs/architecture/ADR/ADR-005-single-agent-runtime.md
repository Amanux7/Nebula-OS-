# ADR-005: Bounded Single-Agent Decision Protocol

## Status

Accepted, 2026-09-03. Next available ADR number; no live-provider ADR is needed
because Stage 2 deliberately implements only the required scripted adapter.

## Context

ADR-002 deferred Action/Observation payloads and ADR-003 deferred AgentRun storage.
Stage 2 requires one agent to propose internal actions without owning domain state,
authority, time, or completion. Stage 1 required verification and small store-guard
corrections before this work; its actual results are in the Stage 1 report.

## Decision

### Configuration and participation

AgentDefinition is stable workspace-scoped lineage. AgentDefinitionVersion is an
immutable published snapshot of instructions, role, model identity, allowed actions,
and autonomy ceiling. Publication is sequential; replacing an existing version is
rejected. Activation/deprecation UX remains deferred.

AgentRun is a standalone immutable, optimistic-versioned runtime record under one
TaskAttempt and Execution. It embeds the exact published configuration and limits.
There is one AgentRun per TaskAttempt and at most one active AgentRun per Execution
in this stage. Duplicate starts/drives fail explicitly. Semantic retries require
new attempts. No daemon, distributed lease, or automatic recovery is introduced.

### Lifecycle and atomic boundaries

AgentRun starts `running`, may move to `waiting`, and resumes to `running`. From
either active state it may fail or cancel; only running may succeed. Terminal runs
never reopen. Lifecycle changes append StateTransitions, while iteration bookkeeping
increments the version without inventing a lifecycle transition.

AgentRuntimeService is separate from the deterministic DomainService. RuntimeStore
owns runtime records and exposes a shared atomic boundary with DomainStore. The
in-memory adapter snapshots both sets of records under one reentrant lock and rolls
back on error. Completion commits AgentRun, TaskAttempt, Task, eligible Execution,
and their audit records together. No model await occurs inside a transaction.
This simple test adapter is neither a durable database nor an event-sourced system.

Each invocation is claimed/versioned before the model call. Afterward the runtime
revalidates the run and all Goal/Task/TaskAttempt/Execution versions, active states,
deadline, schema, policy, and output. Late or cancelled results cannot complete work.

### Protocol and actions

ModelPort is provider-neutral cooperative async: typed AgentModelRequest in,
untrusted JSON string out. Exact-key schema version 1 accepts only:

- `respond`: bounded, explicitly untrusted intermediate message; not completion.
- `request_more_context`: bounded missing-field list from the required fact keys.
- `complete_task`: structured findings and gaps, requiring deterministic validation.

Unknown fields, schema versions, actions, oversized output, duplicate JSON keys,
and malformed data fail closed. No private-reasoning field is requested. Action is
an immutable typed request, Observation is an immutable result/input with provenance
and trust, and Event describes a committed fact. They remain distinct records.

Allowed actions are enforced outside the model. Internal completion requires at
least Level 1; no action can perform an external effect at any autonomy level.
Exactly one supplied agent type exists: Research Brief Agent.

### Grounding and acceptance

The caller supplies a task-scoped, bounded fact fixture and required fact keys.
The model selects exact key/value/source-ID findings. A required key with no value
or conflicting values must be a gap. Every unambiguous required key must have one
exactly matching finding. At least one finding is required to complete. The summary
is rendered from validated facts/gaps by software, not accepted as arbitrary prose.

This is an extractive grounding contract, not a general entailment evaluator or
verification that caller-supplied facts are true. Natural-language Task acceptance
criteria still require product-specific evaluation and eventual human acceptance.
The runtime may complete a Task after this declared structured contract passes; it
does not automatically satisfy the Goal.

### Bounds, wait, and failures

Default limits: 5 iterations, 60 seconds total, 5 seconds per model call, the last
4 Observations, 16,000 context characters, and 8,000 response characters. Configuration
has positive-integer upper bounds. Collection/field limits apply to supplied data.
Limits are per run and survive wait/resume. Source text is explicitly data, not policy.

Model calls use asyncio timeout plus UTC deadline checks before/after invocation.
Adapters must not block the event loop and must cooperate with cancellation. This is
not an isolation boundary against hostile adapter code. A waiting run expires when
next inspected through resume; there is no background expiry worker. Explicit
cancellation invalidates late results; an outstanding invocation may take up to its
remaining timeout to return unless its coroutine is cancelled by the caller.

Requesting context puts the Execution and AgentRun in waiting while the TaskAttempt
stays running and Task stays in_progress. Resume replaces caller-approved context,
preserves IDs, required keys, deadline, and iteration count. No conversational UI.

Provider/schema/policy/budget failure fails the attempt and Execution, returns an
in-progress Task to ready, and leaves the Goal active. Cancellation is separate.
Existing terminal parent records are never rewritten. There are no automatic retries.

## Alternatives

- A generic ExecutionStep, mutable AgentInstance, or chat-history state: rejected
  by prior ADRs and not reintroduced.
- Provider SDK/framework inside core: unnecessary for the scripted proof; deferred.
- Arbitrary model-written narrative as accepted evidence: cannot be deterministically
  grounded by this small fixture contract; deferred rather than falsely certified.
- Holding a lock across the model call: rejected; version snapshots and post-call
  validation allow cancellation and prevent stale completion.
- Full database, worker queue, outbox, or event sourcing: no current requirement.

## Consequences and limits

The runtime is testable offline and preserves configuration identity, bounded
execution, audit correlation, and atomic state changes. Tests prove software
behavior against scripted proposals, not live-model research quality or perfect
prompt-injection resistance. In-memory data vanishes on process exit; snapshot
transactions are intended for this scale, not production load. IDs consumed by a
rolled-back operation may have gaps. Rejected raw outputs are not retained.

## Deferred questions

Live provider selection/conformance, semantic evaluation and human calibration,
durable transactions/recovery, expiry scheduling, source snapshots/retention across
context replacement, policy revocation, authenticated API context, deployment
version identity, and Tool Runtime side-effect controls remain future work.
