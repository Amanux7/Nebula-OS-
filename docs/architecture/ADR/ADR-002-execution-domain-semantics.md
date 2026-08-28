# ADR-002: Execution Domain Semantics

- **Status:** Accepted
- **Date:** 2026-08-27
- **Scope:** Stage 0.1 domain vocabulary and Stage 1 boundaries

## Context

The Stage 0 model used `ExecutionStep` for an atomic action attempt or transition and linked it to Observations and approvals. That name could absorb fundamentally different concepts—model decisions, Tool calls, results, handoffs, approvals, state changes, Workflow transitions, evaluations, and runtime Events. A single polymorphic record would become difficult to validate, query, version, replay, audit, and evaluate.

The model also needed to distinguish logical work from attempts. A Task such as “Research competitor pricing” should survive a provider timeout and retain both the failed and successful attempt histories without being copied or overwritten.

## Decision

### Execution

An Execution is one bounded root attempt to satisfy a Goal, run a Workflow, or handle another explicitly typed top-level invocation. It is workspace-owned, has an initiating principal, explicit bounds, optimistic concurrency version, lifecycle, and outcome/failure reason.

The initial lifecycle is `Created → Running ↔ Waiting → Succeeded | Failed | Cancelled`. Timeout is a failure reason, not a separate status. Cancellation is distinct from failure. A terminal Execution never reopens; restart/retry creates a new linked Execution. Process recovery of the same non-terminal committed attempt retains its identity.

An Execution may coordinate several TaskAttempts. Failure of the Execution does not automatically close its Goal as unsatisfied.

### Goal and Task

A Goal is a desired outcome with constraints and acceptance criteria. It owns zero or more Tasks in the initial model and may exist before planning or Execution. Goal satisfaction is explicit. Because process attempts can fail while the outcome remains achievable, the initial Goal terminal states are `Satisfied`, `ClosedUnsatisfied`, and `Cancelled`, rather than overloading `Failed`.

A Task is bounded logical work belonging to exactly one Goal. It may exist before Execution, depend on same-Goal Tasks, be delegated or decomposed, and have acceptance criteria. A TaskAttempt failure does not automatically fail the Task or Goal; deterministic policy chooses retry, block, or explicit Task failure.

### TaskAttempt

TaskAttempt is adopted as a canonical domain entity. It represents one concrete attempt to perform exactly one Task within exactly one Execution. It has a small `Created → Running → Succeeded | Failed | Cancelled` lifecycle. Timeout is a failure reason. A retry creates a new attempt linked by ordinal/predecessor; terminated attempt history is immutable except permitted audit annotations. Stage 1 permits at most one non-terminal TaskAttempt per Task; speculative parallel attempts require a later decision.

### Action

Action is a future canonical runtime entity: a requested operation selected by deterministic logic, Workflow logic, or an Agent. Candidate kinds include `invoke_model`, `call_tool`, `request_approval`, `delegate_task`, `emit_artifact`, and `finish_task`.

Each kind uses a versioned typed payload behind a small common envelope. Action will not be a large nullable object containing every kind's fields. Stage 1 does not implement Action families.

### Observation

Observation is a future canonical append-only runtime record: typed information returned after an Action or external input, including model structured results, Tool results, retrieval results, API responses, and approval responses. It records provenance and trust classification and remains untrusted until validated. An Observation or referenced receipt—not an Action or state label—provides evidence about external outcomes. Stage 1 does not implement Observation payload families.

### StateTransition

StateTransition is adopted as an explicit append-only history record for Goal, Task, TaskAttempt, and Execution lifecycle changes. The subject also stores canonical current state for direct validation and querying. The current-state update and transition append must be atomic within the chosen persistence boundary.

Reconstructing current state only from Events is rejected for the initial architecture. Explicit transition history provides auditability without requiring full event sourcing.

### Event

Event is adopted as a minimal versioned append-only record of selected significant committed facts, such as `execution_started`, `task_attempt_failed`, or `approval_requested`. It may reference StateTransitions, Actions, and Observations.

An Event/audit record is not a commitment to event sourcing. Current records remain canonical; Stage 1 needs no Event replay engine, CQRS architecture, broker, outbox, or distributed delivery. Those mechanisms require separate evidence and decisions.

### ExecutionStep

`ExecutionStep` is removed from the canonical domain vocabulary. User-facing timelines and Workflow definition steps may still use the ordinary word “step,” but no generic runtime entity combines attempts, Actions, Observations, transitions, and Events.

## Alternatives Considered

### Keep ExecutionStep with a type discriminator

It offers one ordered table/collection, but still couples unrelated lifecycles and payload schemas and encourages consumers to switch over an expanding union. Rejected as the canonical model. A future trace projection may unify records for display without becoming domain truth.

### Treat Execution as one Task attempt

This is simple for single-task work but cannot naturally represent one bounded Goal/Workflow attempt coordinating multiple Tasks. Rejected. TaskAttempt provides the narrower attempt boundary.

### Put retry count and last error directly on Task

This loses historical attempts, ambiguous outcomes, assignee/configuration versions, and evaluation evidence. Rejected.

### Reconstruct all state from Events

Provides event-sourcing capabilities but adds replay, evolution, ordering, snapshot, and operational complexity not required by Stage 1. Rejected as the default architecture.

### Store only current state with normal logs

Simpler, but insufficient for lifecycle auditing, concurrency diagnosis, and reproducible tests. Rejected; minimal StateTransition history is justified.

## Consequences

### Positive

- Logical work and retry history are independently queryable.
- Action requests cannot be confused with results or state changes.
- Small state machines and explicit concurrency guards are testable without AI or infrastructure.
- Auditing does not force event sourcing.
- Future trace UIs can project one timeline from typed records.

### Costs

- More domain nouns and correlations must be learned.
- Atomic current-state/StateTransition persistence requires care when a real adapter is added.
- Cross-record ordering and retention rules need later decisions.
- Action and Observation families need versioning discipline in their implementation stages.

## Deferred Questions

- Whether AgentRun is stored separately or embedded in invocation/TaskAttempt records.
- Exact Action and Observation kind schemas and lifecycles.
- Event retention, delivery guarantees, consumers, and whether an outbox is ever required.
- Whether all accepted transitions produce Events or only an allowlist of significant facts.
- Workflow representation and the relationship between Workflow definition steps and runtime Actions.
- Compensation semantics and partial Goal satisfaction.
