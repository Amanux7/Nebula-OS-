# ADR-001: Foundational Architecture Principles

- **Status:** Accepted
- **Date:** 2026-08-27
- **Scope:** Stage 0 direction; technology-neutral

## Context

Agent Company OS must eventually coordinate reasoning, deterministic work, external actions, knowledge, memory, approvals, and multiple actors. Early prototypes often optimize for visible agent count or framework features while obscuring state, permissions, and failure. Those choices would make trustworthy autonomy and later replacement difficult.

## Decision

1. **Build and validate the underlying runtime before a large agent catalog.** The initial product uses only agents justified by a complete workflow.
2. **Keep Agent, Skill, Tool, Task, and Workflow distinct.** They have different ownership, versioning, execution, and security semantics.
3. **Treat visualization as a projection.** Org and execution graphs reflect canonical definitions and state; they are not the source of truth.
4. **Make execution semantics explicit and durable when required.** Goal, Task, TaskAttempt, and Execution have distinct lifecycles; Action, Observation, StateTransition, and Event are not collapsed into a generic step record.
5. **Bound and permission autonomy.** Effective authority is least-privileged; consequential actions are policy-checked and approval-capable.
6. **Prefer deterministic workflows when deterministic logic is sufficient.** Reasoning is used for ambiguity, synthesis, and judgment, not routine control flow.
7. **Do not commit the core to a large agent framework until runtime needs are understood.** Libraries may be used behind typed ports after evaluation.
8. **Do not store hidden chain-of-thought.** Persist structured decisions, evidence references, tool requests/results, and state transitions.
9. **Use AI for judgment and software for guarantees.** Planning strategies may be deterministic, agentic, or hybrid, but domain validation, workspace isolation, permissions, bounds, version consistency, idempotency, and approvals remain deterministic enforcement concerns.
10. **Make infrastructure earn its place.** Stage 1 begins with an application, typed domain layer, and in-memory/test adapters; databases, queues, brokers, workflow engines, frameworks, event sourcing, and service splits require demonstrated needs and separate decisions.

## Alternatives considered

### Build many role-specific prompt wrappers first

Faster visual breadth, but creates duplication, unclear capability boundaries, shallow evaluations, and pressure to hard-code an organization. Rejected for the foundation.

### Adopt a comprehensive agent framework as the architecture

May accelerate a prototype and provide integrations, but can impose state, tracing, and orchestration semantics before requirements are known. Rejected as an irreversible foundation; individual frameworks remain candidates behind adapters.

### Make the graph editor canonical

Visually intuitive, but couples data integrity and runtime semantics to one UI representation and makes non-graph use cases awkward. Rejected; graphs remain projections/editing clients over validated contracts.

### Model every operation as agentic

Creates unnecessary nondeterminism, latency, cost, and testing difficulty. Rejected; deterministic steps remain first-class.

### Store execution primarily as chat history

Simple for prototypes, but hides lifecycle, policy, retries, idempotency, and durable recovery. Rejected.

### Use one polymorphic ExecutionStep record

Offers a convenient timeline shape but conflates logical attempts, requested operations, returned information, state changes, and audit facts. Rejected as canonical domain vocabulary; trace projections may still combine typed records for display.

## Consequences

### Positive

- Core concepts can evolve independently with typed contracts.
- Security, approval, replay, evaluation, and observability have clear enforcement points.
- Provider/framework replacement remains practical.
- The MVP tests useful end-to-end behavior instead of agent quantity.
- Deterministic tests can cover state and policy without live models.

### Negative and costs

- Upfront domain and state-machine design slows visible feature delivery.
- Adapters and structured schemas require maintenance.
- Framework conveniences may need wrapping or cannot be used directly.
- The product must resist pressure to present conceptual agents as implemented features.

### Follow-up decisions

[ADR-002](ADR-002-execution-domain-semantics.md) defines Execution, TaskAttempt, Action, Observation, StateTransition, and Event semantics. [ADR-003](ADR-003-agent-definition-and-runtime-identity.md) defines AgentDefinition, AgentDefinitionVersion, and AgentRun terminology. Separate ADRs are still required for implementation language, any production persistence or job infrastructure, model adapter, Workflow representation, tenancy enforcement, retrieval, Memory promotion, and production deployment when their roadmap stage provides evidence.
