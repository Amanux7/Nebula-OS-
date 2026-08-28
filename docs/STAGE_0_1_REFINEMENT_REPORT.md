# Stage 0.1 Architecture Refinement Report

## 1. Issues Reviewed

1. **ExecutionStep ambiguity:** reviewed whether model decisions, Action requests, Observations, approvals, transitions, evaluations, and Events should share one runtime object.
2. **AgentDefinition versus runtime identity:** reviewed immutable configuration versioning and whether `AgentInstance` is a justified persistent entity.
3. **Goal versus Task precision:** reviewed outcome, work decomposition, attempt, retry, delegation, dependency, and failure semantics.
4. **Replaceable orchestration:** preserved the open deterministic/agentic/hybrid choice while defining a stable seam around core state machinery.
5. **Memory boundaries:** separated current Working State, Conversation History, Episodic Memory, Semantic Memory, and authoritative Knowledge and checked Stage 1 scope.
6. **Premature infrastructure:** reviewed whether Stage 1 needs a database, queue, workflow engine, broker, Agent framework, microservices, or event sourcing.

## 2. Decisions Made

### Execution vocabulary

- **Execution** is one bounded root attempt to satisfy a Goal, run a Workflow, or handle another typed top-level invocation. It may coordinate multiple TaskAttempts.
- **TaskAttempt** is adopted as the canonical attempt to perform exactly one Task within one Execution. Retry creates a new attempt and preserves terminated history.
- **Action** is a future typed canonical runtime request selected by software, Workflow logic, or an Agent. Different Action kinds use versioned kind-specific payloads.
- **Observation** is future immutable typed information returned after an Action or external input. It has provenance/trust metadata and remains untrusted until validated.
- **StateTransition** is an explicit append-only lifecycle history record stored alongside the subject's canonical current status.
- **Event** is a minimal append-only record of a selected significant committed fact. Events support audit/projections but do not make the system event-sourced.
- **ExecutionStep** is not a canonical domain entity. A future trace timeline may project all typed records without storing them as one polymorphic object.

### Lifecycles

- Goal uses a small initial lifecycle: `Draft`, `Active`, `Satisfied`, `ClosedUnsatisfied`, and `Cancelled`. `Failed` is not used because attempt failure does not prove the outcome is impossible.
- Task separates logical work from attempts and may move through `Proposed`, `Ready`, `InProgress`, `Blocked`, and explicit terminal outcomes.
- TaskAttempt and Execution use small attempt-oriented lifecycles. Timeout is a failure reason rather than an additional status. Cancellation is distinct from failure.
- A terminal TaskAttempt or Execution is not reopened. A semantic retry creates a linked new attempt; recovery of the same non-terminal committed attempt retains identity.

### Agent configuration and runtime identity

- **AgentDefinition** is stable workspace-scoped configuration identity and version lineage.
- **AgentDefinitionVersion** is immutable behavior configuration. Historical records bind the exact version plus immutable/transitively versioned dependencies or an effective content-addressed snapshot/hash.
- **AgentRun** replaces `AgentInstance` as the future bounded participant created for one TaskAttempt from one AgentDefinitionVersion.
- **AgentInvocation** is only the command/request to start an AgentRun.
- AgentRun persistence remains deferred; Stage 1 may model only minimal AgentDefinition/version reference types and implements no Agent behavior.

### Goal and Task

- A Goal describes desired success, not implementation steps, and may exist before planning, Tasks, or Execution.
- A Task is bounded logical work, belongs to exactly one Goal in the initial model, may exist before Execution, may depend on/decompose into same-Goal Tasks, and has acceptance criteria.
- A failed TaskAttempt does not automatically fail its Task or Goal. Deterministic policy selects retry, blocking, explicit Task failure, or another path; Goal closure remains explicit.

### Orchestration seam

- Agentic, deterministic, and hybrid planning remain valid future strategies.
- A provisional `PlanningPort` returns a typed Structured Plan proposal to an Orchestration Coordinator.
- The coordinator applies plans only through normal Goal, Task, TaskAttempt, and Execution commands and validation.
- Planning cannot mutate state directly, widen permissions, execute Tools, or declare success. Core domain logic does not depend on a specific planner.
- Governing principle: **AI for judgment. Software for guarantees.**

### Memory and Knowledge

- Working State is short-lived deterministic information required for the current attempt.
- Conversation History is interaction history and is not automatically Context or Memory.
- Episodic Memory is possible future retention about prior experiences/Executions.
- Semantic Memory is possible future distilled/retrievable learned information.
- Knowledge is internally or externally authoritative information with provenance and freshness.
- Future generated Memory cannot silently override authoritative Knowledge. Stage 1 has no `memory`, `agent_memory`, MemoryEntry, embedding, or retrieval system.

### Infrastructure

- Stage 1 begins with an application, typed domain layer, typed ports, deterministic clock/ID providers, and in-memory/test persistence adapters.
- Stage 1 does not require a production database, queue, worker, cache, message bus, Workflow engine, vector store, Agent framework, microservices, CQRS, or event sourcing.
- A primary language/project structure may be selected through evidence. Any database or external infrastructure introduced earlier than its demonstrated need requires an ADR.

## 3. Terminology Changes

| Previous terminology | Stage 0.1 terminology | Result |
|---|---|---|
| `ExecutionStep` | TaskAttempt, Action, Observation, StateTransition, and Event | Removed as canonical runtime/domain entity. |
| Task with implicit retry history | Task plus TaskAttempt | Logical work separated from each attempt. |
| `AgentInstance` | AgentRun | Renamed to emphasize bounded runtime participation; persistence deferred. |
| “Agent Definition version” as one object | AgentDefinition plus AgentDefinitionVersion | Stable lineage separated from immutable behavior version. |
| Agent Invocation as possible identity | AgentInvocation command plus AgentRun participant | Command and runtime identity separated. |
| Generic “memory” | Working State, Conversation History, Episodic Memory, Semantic Memory, Knowledge | Lifecycle and authority categories separated. |
| Orchestration layer with implicit strategy | PlanningPort/Structured Plan strategy seam plus Orchestration Coordinator | Strategy remains replaceable; state machinery remains independent. |

## 4. Domain Invariants Added

- Every workspace-owned record and relationship stays inside exactly one Workspace; cross-workspace references are invalid.
- Terminal Goals cannot silently return to active; Stage 1 has no reopen transition.
- Attempt/Execution failure does not automatically close a Goal.
- A Task belongs to exactly one Goal in the initial model, has acceptance criteria, and has one current status.
- Task dependencies/decomposition stay in the same Workspace/Goal and are acyclic under the initial policy.
- Each TaskAttempt belongs to exactly one Task and one Execution; terminated history is immutable except allowed audit annotations.
- Stage 1 permits at most one non-terminal TaskAttempt per Task; speculative parallel attempts remain deferred.
- Failed and Cancelled are distinct; timeout is a failure reason.
- Terminal Executions do not resume; retries/restarts create linked Executions, while recovery keeps a non-terminal identity.
- Mutable lifecycle updates use optimistic concurrency/version guards.
- Action, Observation, StateTransition, and Event are not interchangeable or stored as generic ExecutionStep payloads.
- Current state plus StateTransition history is canonical; Events do not imply event sourcing.
- Historical Agent behavior binds an exact immutable AgentDefinitionVersion and behavior-affecting dependencies/snapshot.
- No state or transition alone proves an external side effect; later success requires receipt/reconciliation evidence.
- Stage 1 has no generic Memory field, and future generated Memory cannot silently override Knowledge.

## 5. Deferred Decisions

- AgentRun as a standalone persistent entity versus a typed record under TaskAttempt.
- Exact Action/Observation kind schemas, lifecycles, storage shape, and retention.
- Which lifecycle changes emit Events and whether later consumers require an outbox, broker, or delivery guarantee.
- Planning strategy per workflow: deterministic, agentic, or hybrid.
- Workflow graph/statechart representation, compensation, and partial Goal satisfaction.
- AgentDefinitionVersion activation, rollback, migration, and transitive snapshot policy.
- Memory ownership, promotion, validation, retrieval, conflict resolution, and retention.
- Primary implementation language and project structure.
- Production database, job runner, deployment topology, and all other infrastructure until requirements demonstrate need.

## 6. Stage 1 Scope After Refinement

Stage 1 is **Deterministic Domain Foundation** and should implement only:

- Workspace identity and scope;
- opaque IDs and versioned schemas;
- Goal, Task, TaskAttempt, and Execution lifecycles;
- explicit StateTransition history;
- a minimal versioned Event/audit envelope without a broker or replay architecture;
- deterministic clock and ID ports;
- optimistic concurrency/version guards;
- typed command/query and repository boundaries;
- in-memory/test persistence adapters;
- minimal AgentDefinition/AgentDefinitionVersion reference semantics only if needed for historical binding;
- workspace isolation, complete transition-table, retry-lineage, terminal-state, concurrency, schema, and serialization tests;
- repository quality tooling and CI.

Stage 1 completion requires deterministic scenarios and tests with no network or production infrastructure service.

## 7. Explicitly Not Added

This refinement added no:

- LLM integration or model provider;
- AgentRun implementation, reasoning loop, or AI behavior;
- Tool execution, external action, MCP, or integration;
- RAG, embedding, Knowledge ingestion/retrieval, or vector store;
- Memory system, MemoryEntry implementation, or generic Memory field;
- planning/orchestration implementation or multi-agent communication;
- production database, queue, worker, Redis, Kafka, Temporal, Celery, BullMQ, or message bus;
- LangGraph, CrewAI, AutoGen, or other Agent framework;
- microservices, CQRS, event sourcing, complex Workflow DSL, graph UI, or autonomous action.

Only documentation and architectural decisions were refined.

## 8. Recommended Next Action

**Ready for Stage 1.**

Begin only after explicit authorization, and implement the deterministic scope above without starting Stage 2 capabilities.
