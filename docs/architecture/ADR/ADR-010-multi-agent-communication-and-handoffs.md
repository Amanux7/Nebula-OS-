# ADR-010: Multi-Agent Communication and Handoffs

## Status

Accepted — Stage 7, 2026-09-04.

## Context

Stage 6 coordinates canonical Tasks through immutable plans, Delegations, and exact
AgentRuns. Runtime participants now need a narrow way to exchange clarification and
provenance or request substantial-work transfer. Treating this as free-form chat,
shared memory, a blackboard, or a message broker would obscure ownership, leak scoped
references, and let message text masquerade as authority. The protocol must remain
bounded, point-to-point, inspectable, and subordinate to orchestration.

## Decision

Multi-agent communication is the controlled exchange of typed, bounded,
provenance-aware work information between runtime participants in one workspace and
one OrchestrationRun. It is not a social/chat system, canonical Task state, Knowledge,
Memory, or permission transfer.

### Messages and threads

`AgentMessage` is the immutable message envelope. It snapshots exact sender and
recipient AgentRun and AgentDefinition versions; source and recipient Tasks and
Delegations; one thread; kind; typed payload; references; correlation; policy/schema
versions; deadline; and timestamps. Only status metadata evolves. Supported kinds are
`information`, `request`, `response`, `handoff_request`, `handoff_accept`,
`handoff_reject`, and `handoff_result`. Stage 7 application commands use information,
request, and response directly; the handoff record is the canonical transfer contract.

Payloads are typed as `InformationPayload`, `RequestPayload`, `ResponsePayload`,
`HandoffRequestPayload`, or `HandoffResultPayload`. Human-readable fields are bounded.
`MessageThread` groups one bounded correlation scope inside one OrchestrationRun. It is
not a public channel or agent inbox. Delivery is direct and in-process. `delivered`
means persisted and available; it does not mean consumed, accepted, or acted upon.

### Policy, delivery, and idempotency

`CommunicationPolicy` controls message kinds, reference kinds, recipient roles,
message/payload/reference counts, per-thread/per-AgentRun/per-OrchestrationRun totals,
request counts, context count, handoff count/depth, and response timeout. Both exact
AgentDefinitionVersions must opt in, and the sender grants exact recipient roles.
Recipient AgentRuns must be active, delegated participants in the same Goal and
OrchestrationRun. Planner or message content cannot widen policy.

The host supplies an `AgentMessageId`. Replaying that ID returns the existing message
without redelivery; a new ID represents a new intentional message. This is local
idempotency, not distributed exactly-once delivery. Requests and responses bind through
`in_reply_to` plus an exact correlation ID and reversed participants. Late responses
to terminal requesters are rejected. Timeouts are evaluated lazily with a deterministic
Clock. There is no automatic resend.

### References and context

Messages contain bounded summaries and typed references, not copied histories. Stage 7
supports TaskResultReference, ToolReceipt, EvidencePack, and MemoryContextPack reference
kinds. Before delivery the runtime validates source scope and independently reauthorizes
the exact recipient: Tool grants must match exact versions; every Knowledge source/trust
must be allowed; every Memory scope/sensitivity must be allowed; Task results must exist
in the same orchestration lineage. “Sender can access” never implies “recipient can.”

`AgentMessageContext` is a bounded, deterministically ordered snapshot in a separate
`AgentModelRequest.agent_messages` section. Message payload is labeled
`untrusted_agent_message`; it is not supplied fact evidence, Knowledge, Memory, a tool
receipt, or completion grounding. Messages never auto-promote to Memory.

### Handoffs

`HandoffRequest` is an explicit participant request that substantial work be transferred.
It snapshots sender identity/version, source Task/Delegation, requirements, references,
parent/depth, deadline, policy/schema, resolution, resulting Delegation, and result
lineage. System acceptance is explicit status metadata; a separate HandoffDecision
entity would duplicate the single deterministic resolver and is not added.

A Handoff is not a Delegation. The participant requests transfer; deterministic policy,
the existing AgentSelector, and OrchestrationService resolve it. Acceptance ends the
sender attempt without cancelling the logical Task, selects a different eligible exact
definition, and creates a normal redelegation. Completion requires the resulting
canonical AgentRun result and records its TaskResultReference. Depth is two by default;
ancestor definitions are excluded to stop obvious ping-pong. Failure or exhaustion
escalates rather than constructing hidden work.

### Storage, events, and atomicity

`CommunicationStore` is an in-memory adapter sharing the orchestration/runtime atomic
boundary. Message creation/delivery and handoff resolution/delegation roll back together
on failure. Minimal Events cover message creation/delivery/rejection/consumption,
handoff request/accept/reject/complete/failure, and timeout. Canonical state is stored
directly; this is not event sourcing or a durable transport.

## Alternatives

- Free-form agent chat, broadcast, pub/sub, gossip, or inbox polling: rejected because
  they create unbounded context and weak provenance without a Stage 7 requirement.
- Shared mutable blackboard: rejected because ownership, concurrency, and authority
  become ambiguous.
- Kafka, RabbitMQ, NATS, Redis Streams, or a durable workflow/message service: deferred;
  the current requirement is deterministic in-process semantics.
- Let messages create Tasks or reassign work directly: rejected. Significant work goes
  through a Handoff and canonical orchestration Delegation.
- Trust sender authority for references: rejected. Recipient access is reauthorized.
- Add model `send_message`/`request_handoff` actions now: deferred. Typed host commands
  prove policy and lifecycle without prematurely widening the untrusted action surface.

## Consequences

- Communication is attributable, bounded, versioned, and reproducible.
- Exact role grants and reference checks reduce impersonation and authority laundering.
- Agent context remains separated by authority category.
- Handoffs preserve canonical Task/Delegation/AgentRun lineage.
- Synchronous in-memory delivery has no process-loss recovery or distributed ordering.
- Opt-in communication grants require deliberate AgentDefinition configuration.
- Structural validity is proven; usefulness and live-model communication quality are not.

## Deferred Questions

- Which model action schemas and evaluations justify agent-proposed communication?
- Durable delivery, claims, leases, retries, ordering, and process-loss recovery.
- Authenticated principals, policy administration, privacy deletion, and retention.
- Semantic usefulness, unnecessary-message detection, and live-model quality gates.
- Redaction or transformed reference delivery when full recipient access is denied.
- Human participation, external messaging providers, and approval interactions.
- Organization/department routing and discovery (Stage 8).
- Broadcast, pub/sub, shared artifacts, MCP, and graph UI remain unimplemented.
