# Open Questions

These decisions are intentionally unresolved. “Target stage” indicates when evidence is expected, not a deadline to decide prematurely.

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
