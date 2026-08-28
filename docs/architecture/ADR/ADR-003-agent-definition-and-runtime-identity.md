# ADR-003: Agent Definition and Runtime Identity

- **Status:** Accepted
- **Date:** 2026-08-27
- **Scope:** Stage 0.1 terminology and historical behavior identity

## Context

Stage 0 distinguished `AgentDefinition` from `AgentInstance`, but `AgentInstance` remained ambiguous. It could mean an invocation, a long-lived persona, a session, an in-memory object, or a persistent runtime record. Encoding it prematurely would create accidental lifecycle and storage commitments.

Historical Execution analysis requires stronger semantics: changing an agent's instructions, allowed capabilities, knowledge policy, autonomy ceiling, Policy references, or model configuration must not silently change the meaning of prior behavior.

## Decision

### AgentDefinition

AgentDefinition is the stable workspace-scoped logical identity and version lineage for an agent configuration. It may hold name, description, ownership, and lifecycle/activation metadata conceptually. It is configuration identity, never active execution.

### AgentDefinitionVersion

AgentDefinitionVersion is the immutable published behavior configuration. Conceptually it may include role and description, instruction reference/version, allowed Skill and Tool references, knowledge access policy, autonomy ceiling, Policy references, model policy/configuration, and creation metadata. Draft/publication and activation/deprecation metadata may change without mutating the published behavior payload; exact storage fields remain deferred.

Once referenced by runtime history, the version and every behavior-affecting dependency must be immutable or transitively versioned/content-addressed. A mutable “active” alias may select a version before a run but cannot be the only historical reference.

### AgentRun

`AgentRun` replaces `AgentInstance` as the selected term for future runtime participation. An AgentRun is bounded participation created from exactly one AgentDefinitionVersion for a TaskAttempt within an Execution. It may contain a runtime configuration snapshot/reference, effective Policy, bounds, status, timing, and outcome.

AgentRun is not implemented in Stage 1. Stage 2 will determine whether it requires a standalone persistent entity or is adequately represented by an invocation/run record associated with TaskAttempt. The term is fixed; storage form is deferred.

### AgentInvocation

AgentInvocation means the command/request to start an AgentRun. It is not the participant's identity and is not a synonym for Execution or TaskAttempt.

### Historical reproducibility

Every future AgentRun, and the TaskAttempt/Execution trace that contains it, must identify the exact AgentDefinitionVersion used. The record must also preserve either exact immutable references to all behavior-affecting configuration or a content-addressed effective snapshot/hash. Provider/model identifier, relevant runtime configuration, Skill/Tool definition versions used, and Policy/evaluator versions are recorded when those capabilities exist.

Reproducibility means historical interpretation, debugging, comparison, and evaluation are possible. It does not promise bit-for-bit re-execution from a probabilistic provider or changing external systems.

## Alternatives Considered

### Keep AgentInstance

Common in object-oriented designs, but semantically suggests a durable mutable object or long-lived virtual employee. It does not communicate bounded execution. Rejected.

### Use AgentInvocation as runtime identity

Clear for a request envelope but conflates the command to start work with the resulting participant and lifecycle. Rejected as identity; retained for the command.

### Use RuntimeActor

Broad enough for humans, services, and Agents, but loses the important link to versioned agent behavior. It may be useful as a generic authorization principal later, not as the Agent-specific run term.

### Store only a snapshot on Execution

Can preserve history but duplicates configuration across multiple AgentRuns and obscures version lineage. Rejected as the sole identity mechanism; a snapshot/hash may complement the required version reference.

### Reference only the active AgentDefinition

Simple, but historical meaning changes when active configuration changes. Rejected.

## Consequences

### Positive

- Configuration identity, immutable behavior version, start command, and runtime participation are unambiguous.
- Historical audit and evaluation can group by stable definition or exact version.
- Stage 1 avoids inventing a persistent runtime object before the runtime exists.
- Future definition changes cannot silently reinterpret history.

### Costs

- Version lineage and transitive behavior references require discipline.
- Activation/deprecation and snapshot policies need later design.
- Queries may need both logical definition and version identifiers.
- Exact re-execution still depends on external/model availability and is not guaranteed.

## Deferred Questions

- Whether AgentRun is a standalone persistent entity or a typed record under TaskAttempt.
- Which behavior-affecting dependencies are copied, content-addressed, or referenced by immutable version.
- Draft, activation, deprecation, rollback, and migration UX for AgentDefinitionVersions.
- How model/provider aliases resolve to concrete runtime metadata.
- Whether non-agent runtime participants share a general actor/run abstraction.
