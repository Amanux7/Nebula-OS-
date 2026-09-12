# Open Questions

## Stage 9 consequential-action governance

ADR-012 resolves exact intent/digest binding, Levels 0–3 policy, explicit local reviewer
allowlists, single-use reservation/consumption, lazy expiry, current-policy revalidation,
organization-aware write invalidation, waiting/resume, and fixture-only execution.
Approval is not a grant; manager is not approver. High-risk and Level 4 writes stay denied.

Still open: authenticated reviewer/admin identity, separation of duties/multi-party
review, human preview comprehension, durable claim recovery/reconciliation, real
connector idempotency and compensation, retention/redaction, production rate limits,
and safe emergency revocation across distributed systems. Recommend reliability and
audit-query foundations for Stage 10 before production writes or approval/graph UI.

## Stage 8 organizational foundation

ADR-011 resolves flat department membership, one reporting parent, cycle/depth limits,
one active lead, immutable whole-graph versions, atomic activation, exact registry
references, and pinned history. Organization narrows existing authorization.

Still open: authenticated administrators; emergency revocation for pinned structure;
department-context routing for matrix membership; overlapping lead windows; durable
transactions/recovery; privacy, redaction, and revision retention; UI/editor and analytics;
calibrated routing quality. No self-promotion, dynamic hiring/firing, LDAP/SCIM, or
autonomous restructuring is implemented.

These decisions are intentionally unresolved. “Target stage” indicates when evidence is expected, not a deadline to decide prematurely.

## Stage 7 decision updates

- OQ-008: ADR-010 selects bounded point-to-point AgentMessages, exact correlation,
  immutable participant/configuration provenance, and explicit orchestration-mediated
  HandoffRequests. Broadcast, pub/sub, inbox polling, and shared blackboards are absent.
- OQ-029/030: Stage 7 adds typed communication/handoff records and minimal audit Events;
  it does not reintroduce ExecutionStep or event sourcing.
- OQ-023: direct in-process delivery proves semantics. No queue, broker, distributed
  transport, retry protocol, or process-loss recovery technology is selected.
- OQ-031: substantial peer work escalates to a Handoff and canonical redelegation;
  small bounded clarification remains a message. Partial Goal success is still open.

New questions: which evaluated workflows justify model-proposed communication actions;
what delivery durability/ordering is required; how privacy deletion and sensitive
redaction apply; whether reference transformation is useful when full forwarding is
denied; and how Stage 8 departments constrain discovery and role grants.

## Stage 6 decision updates

- OQ-005: ADR-009 selects a replaceable strategy port and ships a deterministic
  research/analysis/report strategy plus a scripted fake. Whether and where to use a
  model-driven or hybrid planner remains an evaluation question, not a domain change.
- OQ-006/007: accepted plans are immutable bounded DAG snapshots; readiness is derived
  from canonical Task completion. Stage 6 uses in-process orchestration state and does
  not select a durable workflow system.
- OQ-031: runtime failure does not automatically fail a Goal. Bounded retry,
  redelegation, and replan may recover; otherwise the OrchestrationRun waits with an
  escalation reason. Partial Goal satisfaction and compensation remain unresolved.
- OQ-029/030: Stage 6 adds typed proposal/delegation/result records and minimal audit
  Events without introducing a generic ExecutionStep or event sourcing.

New questions: what business evidence warrants model-driven planning; whether accepted
plans may supersede/remove already materialized Tasks; how semantic result quality and
partial success are judged; what durable claim/lease/recovery protocol is needed for
distributed workers; and how Stage 7 messages differ from Delegations and result
references. No queue, workflow engine, planning framework, or planner model is selected.

## Stage 5 decision updates

- OQ-012: ADR-008 selects explicit exact scope/sensitivity grants on immutable
  AgentDefinitionVersions. No global default or cross-scope sharing is implemented.
- OQ-013: host-derived candidates, review-only promotion, exact provenance,
  non-destructive lifecycle, deterministic retrieval, and separately labeled
  MemoryContextPacks are implemented. Memory never grounds completion or overrides
  authoritative Knowledge; conflicts are preserved and flagged.
- OQ-015: the Stage 5 adapter requires a named human reviewer for promotion,
  rejection, and revocation. Authenticated roles, UI, deletion rights, separation of
  duties, and production privacy operations remain unresolved.
- OQ-029/030: no model memory-write Action is added. Minimal candidate/entry/retrieval
  Events are audit records, not event sourcing or a durable delivery contract.

New questions: which real workflows justify auto-promotion; what deletion/redaction
and retention duties apply by scope/sensitivity; whether confidence is useful beyond
authority/provenance; what corpus evidence warrants semantic retrieval; and how
reviewer authorization and concurrent policy changes are linearized in production.
No database, vector index, queue, or memory framework is selected.

## Stage 4 decision updates

- OQ-014: ADR-007 selects bounded lexical-overlap retrieval over text/Markdown/typed
  facts as the offline baseline. Semantic/hybrid retrieval needs corpus/query evidence.
- OQ-029: retrieval is an internal host capability, not a new model Action or tool.
  Exact EvidencePacks enter a dedicated model-context field. Agent query selection is deferred.
- OQ-030/033: source/query/pack Events and immutable packs now preserve accepted
  knowledge evidence after context replacement. Durability, deletion/redaction,
  retention, and complete caller-context history remain unresolved.
- OQ-034: exact source versions and timestamps plus deterministic conflict-gap tests
  now exist. Business freshness, conflict adjudication, semantic grounding, and live
  tool/knowledge-selection quality are still open.
- OQ-036: direct source/trust grants, scope checks, and in-process revocation rechecks
  are implemented. Authenticated publisher/reader identities and production policy
  linearization are not solved by the trusted host test adapter.
- OQ-012/013/015: Memory ownership, promotion/review, expiry, deletion, and precedence
  remain Stage 5 questions. ToolReceipts and EvidencePacks are not automatically Memory.

New questions: what scale justifies an index/database beyond the 100-source workspace
cap; what effective dates/refresh rules define stale knowledge; which free-text
entailment evaluator is sufficiently calibrated; and when an agent-requested retrieval
action earns its added policy and evaluation surface. No new infrastructure is selected.

## Stage 3 decision updates

The inventory below preserves the original questions; these explicit resolutions
and narrower remaining questions take precedence:

- OQ-016: ADR-006 selects immutable exact tool grants and four coarse risk classes;
  only read_only executes. Fine resource scopes, approval defaults, and production
  permission revocation still need Stage 9/12 evidence.
- OQ-028 was resolved by ADR-005: AgentRun is a standalone versioned runtime record
  bound to TaskAttempt. Stage 3 does not reopen that decision.
- OQ-029 now includes call_tool and typed receipt-backed tool Observations under
  ADR-006; approval, retrieval, and delegation families remain deferred.
- OQ-030 gains four minimal tool audit event types and bounded canonical receipts;
  retention, durable delivery, and process-loss recovery are still open.
- OQ-021 remains answered by ADR-004 (Python); Stage 3 adds no language or dependency.
- OQ-022: the custom typed runtime continues to meet this narrow offline scope;
  no framework or production orchestration strategy is selected.

New questions for later stages:

| ID | Question | Evidence needed | Target stage |
|---|---|---|---|
| OQ-032 | How should pending tool claims and unknown outcomes recover after process loss? | Durable transaction/worker-loss fixtures; integration idempotency contracts. | Before production tools |
| OQ-033 | What receipt and caller-source retention, deletion, redaction, and artifact limits are required? | Privacy requirements, audit needs, real source sizes. Tool snapshots exist; caller-context replacement history is not solved. | Stage 4/13 |
| OQ-034 | How should source freshness, conflicts, and tool-selection quality be evaluated? | Versioned corpus and calibrated human/live-model evaluations, beyond exact fact matching. | Stage 4/11 |
| OQ-035 | What isolation and streaming/transport bounds are needed for real executors? | Threat model, adapter conformance, cancellation and allocation failures. In-process fixture limits are not a sandbox. | Before external adapters |
| OQ-036 | What authenticated principal/resource scopes and revocation linearization are required? | API identity and concurrent policy-change scenarios; current scope/grants assume a trusted caller. | Stage 9/12/13 |

## Product and MVP

| ID | Question | Why it matters | Evidence needed | Target stage |
|---|---|---|---|---|
| OQ-001 | Which persona and reference workflow should be the first commercial beachhead? | Drives UX, integrations, evaluation data, and willingness to pay. | Interviews, manual workflow baselines, pilot demand. | Before Stage 2 scope lock |
| OQ-002 | Is Research → Analysis → Report the right MVP workflow, or can a simpler use case validate trust sooner? | Avoids building coordination without user value. | Prototype and single-agent/deterministic comparison. | Stage 2/6 |
| OQ-003 | What minimum explanation makes users trust, correct, and approve work? | Trace UX can be either opaque or overwhelming. | Scenario-based usability research. | Stage 10 |
| OQ-004 | Which Level 3 actions, if any, are safe and valuable immediately after MVP? | Determines approval and integration hardening. | Incident-free Level 2 evidence, risk assessment, user demand. | Stage 9/12 |

## Domain and orchestration

| ID | Question | Why it matters | Evidence needed | Target stage |
|---|---|---|---|---|
| OQ-005 | Which replaceable planning strategy should be used for each workflow: agentic, deterministic, or hybrid? | Changes evaluation, cost, permissions, and failure modes while the PlanningPort seam remains stable. | Stage 2 runtime and Stage 6 planning prototypes against one Structured Plan contract. | Stage 6 |
| OQ-006 | Where should durable Workflow state live and which component owns transitions? | Affects recovery and technology selection. | State-machine scenarios, timer/approval/cancellation requirements. | Stage 1/6 |
| OQ-007 | Should Workflows be sequences, general directed graphs, statecharts, or a constrained combination? | Determines authoring complexity and execution semantics. | Real workflow fixtures, compensation and cycle needs. | Stage 6 |
| OQ-008 | How should agent-to-agent messages and handoffs be represented? | Needed for attribution, ordering, access control, and loop prevention. | Multi-agent failure/use-case scenarios. | Stage 7 |
| OQ-009 | Does Department hierarchy need nesting or membership constraints? | Impacts governance and selection but may add organizational rigidity. | Customer organization patterns. | Stage 8 |
| OQ-010 | How should AgentDefinitionVersion, Skill, and Workflow versions be drafted, activated, deprecated, rolled back, and migrated? | Immutable historical binding is decided, but operational lifecycle and UX remain open. | Stage 1 reference semantics and Stage 8 registry/activation prototype. | Stage 1/8 |
| OQ-011 | What exactly qualifies as a Skill versus Workflow, instruction module, or Tool composition? | Prevents abstraction overlap and unusable registry entries. | Three to five concrete capabilities modeled both ways. | Stage 1/3 |
| OQ-028 | Should AgentRun be a standalone persistent entity or a typed invocation/run record owned by TaskAttempt? | The term is fixed, but persistence should follow Stage 2 query, lifecycle, and audit needs. | Single-agent runtime scenarios and trace queries. | Stage 2 |
| OQ-029 | What are the exact typed Action and Observation families and lifecycles? | They must remain distinct without creating a generic nullable envelope. | Model, approval, retrieval, and Tool scenarios as their stages begin. | Stage 2–4 |
| OQ-030 | Which lifecycle changes produce Events, and what retention/delivery semantics are required? | Minimal audit records are useful, but durable messaging and replay add cost. | Actual projection/integration consumers and operational requirements. | Stage 1 for envelope; later for delivery |
| OQ-031 | How should partial Goal satisfaction and Task compensation be represented? | A failed attempt need not fail a Goal, but complex outcomes need product semantics. | Representative multi-Task workflows and user expectations. | Stage 6 |

## Knowledge and memory

| ID | Question | Why it matters | Evidence needed | Target stage |
|---|---|---|---|---|
| OQ-012 | Do AgentRuns access Agent-scoped, user-scoped, Workspace-scoped, or shared Memory, and who owns each? | Changes privacy, relevance, duplication, and portability. | Episodic/Semantic Memory use cases and isolation experiments. | Stage 5 |
| OQ-013 | How should Episodic Memory and Semantic Memory be promoted, retrieved, and reconciled with authoritative Knowledge? | Prevents stale experience or generated summaries from overriding source truth. | Stage 4 retrieval baseline and Stage 5 conflict fixtures. | Stage 5 |
| OQ-014 | Which retrieval mix—structured queries, full text, semantic search, curated facts—is needed for MVP? | Avoids premature vector-store lock-in and measures grounding. | Representative corpus/query evaluation. | Stage 4 |
| OQ-015 | Who may promote, edit, expire, or delete Memory Entries? | Memory can encode sensitive or false claims. | Persona controls, privacy requirements, poisoning tests. | Stage 5 |

## Security, policy, and data

| ID | Question | Why it matters | Evidence needed | Target stage |
|---|---|---|---|---|
| OQ-016 | How should Tools declare capabilities, risk, resource scopes, and approval defaults? | Drives enforceable least privilege and connector conformance. | Several read/write connector contracts. | Stage 3 |
| OQ-017 | Is a custom policy evaluator sufficient or is a policy language/engine justified? | Affects auditability and operating complexity. | Stage 3/9 rule cardinality and simulation needs. | Stage 9 |
| OQ-018 | Which tenant-isolation mechanism is required at the data layer? | Cross-workspace leakage is critical risk. | Deployment model, admin/support requirements, threat review. | Stage 1/13 |
| OQ-019 | What retention/deletion periods apply to each data category and customer segment? | Impacts privacy, audit, cost, and recovery. | Legal/product requirements and pilot expectations. | Stage 1 then Stage 13 |
| OQ-020 | Which high-impact actions require separation of duties or multiple approvers? | Single approval may be inadequate for critical operations. | Integration risk assessment and customer governance needs. | Stage 9/12 |

## Technology and operations

| ID | Question | Why it matters | Evidence needed | Target stage |
|---|---|---|---|---|
| OQ-021 | Which implementation language best fits the core runtime and product team? | Determines ecosystem, contracts, deployment, and hiring. | Small type/state/async prototypes in TypeScript and/or Python; team constraints. | Stage 1 |
| OQ-022 | How much runtime should be custom versus framework-based? | Balances control and speed against lock-in/hidden semantics. | Stage 2 conformance spike against actual runtime contract. | Stage 2 |
| OQ-023 | When is any production background queue or durable workflow system justified? | Temporal, Celery, BullMQ, Redis, or a database queue add different semantics and operational cost; Stage 1 needs none. | Timer, approval wait, replay, scale, and cancellation requirements from later runtime stages. | Stage 6 or later |
| OQ-024 | Which model/provider capabilities are minimum requirements? | Adapters cannot erase real differences in schema, tools, context, and data policy. | Evaluation workload and provider policy comparison. | Stage 2/11 |
| OQ-025 | Which parts must be separate services or workers at first production deployment? | Service splits should follow real isolation/scale needs. | Load/reliability tests and operational ownership. | Stage 13 |
| OQ-026 | What recovery point/time and availability objectives are justified? | Determines storage, backup, and deployment costs. | Customer impact analysis and pilot expectations. | Stage 13 |
| OQ-027 | For each integration, should we use a direct API, MCP, webhook, or another connector model? | Security and semantics differ by capability. | Per-integration comparison through Tool Runtime contract. | Stage 12 |

## Decision process

The owning stage must turn a material answer into an ADR or versioned requirement, document alternatives and evidence, update affected risks/assumptions, and keep the [Glossary](GLOSSARY.md) consistent.
