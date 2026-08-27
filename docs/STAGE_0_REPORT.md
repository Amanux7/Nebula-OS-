# Stage 0 Completion Report

## Outcome

Stage 0 defines Agent Company OS as a governed operating layer for coordinated AI-assisted work. It establishes a narrow MVP, canonical language, conceptual runtime and data boundaries, permission and approval principles, quality strategies, major risks, and a capability-gated roadmap. It intentionally makes no application or technology-framework commitment.

## Files created or changed

### Repository root

- `README.md` — project overview, current stage, architecture summary, documentation map, and next milestone (replaces the one-line placeholder while preserving repository history).

### Product

- `docs/product/PRD.md` — main product requirements, MVP, FR-001–FR-024, and NFR-001–NFR-012.
- `docs/product/PERSONAS.md` — four role-based persona hypotheses.
- `docs/product/USER_JOURNEYS.md` — eight initial end-to-end journeys and system interactions.
- `docs/product/MVP_SCOPE.md` — MVP, Post-MVP, Future, Out of Scope, and scope gate.
- `docs/product/SUCCESS_METRICS.md` — outcome, reliability, trust, cost, latency, and guardrail metrics.

### Architecture

- `docs/architecture/SYSTEM_ARCHITECTURE.md` — technology-neutral logical layers, boundaries, flows, deployment evolution, and candidate trade-offs.
- `docs/architecture/DOMAIN_MODEL.md` — core entities, conceptual fields, relationships, lifecycles, diagram, and invariants.
- `docs/architecture/AGENT_RUNTIME_ARCHITECTURE.md` — bounded future decision loop and safety/recovery contracts.
- `docs/architecture/DATA_ARCHITECTURE.md` — data categories, authority, tenancy, lifecycle, and candidate stores.
- `docs/architecture/SECURITY_AND_PERMISSIONS.md` — deny-by-default initial permission model, risk classes, approvals, secrets, injection, and autonomous boundaries.
- `docs/architecture/ADR/ADR-001-architecture-principles.md` — accepted foundational architecture decisions and consequences.

### Engineering

- `docs/engineering/ENGINEERING_PRINCIPLES.md` — implementation and review principles.
- `docs/engineering/DEVELOPMENT_ROADMAP.md` — Stages 0–13 with objectives, builds, exclusions, tests, completion criteria, and questions answered.
- `docs/engineering/TESTING_STRATEGY.md` — deterministic layered testing and critical failure scenarios.
- `docs/engineering/EVALUATION_STRATEGY.md` — separation of software tests and agent evaluations, dimensions, datasets, and gates.
- `docs/engineering/OBSERVABILITY_STRATEGY.md` — traces, metrics, logs, audits, correlation, redaction, and service indicators.
- `docs/engineering/RISK_REGISTER.md` — 24 product, AI, security, reliability, and delivery risks with controls and ownership.

### Project

- `docs/project/GLOSSARY.md` — canonical project terminology and autonomy levels.
- `docs/project/ASSUMPTIONS.md` — explicit working hypotheses and validation triggers.
- `docs/project/OPEN_QUESTIONS.md` — unresolved product, domain, knowledge, security, technology, and operational questions.

### Stage report

- `docs/STAGE_0_REPORT.md` — this completion record.

The existing `LICENSE` is preserved unchanged.

## Important product decisions

1. The product is an operating layer for coordinated work, not a chatbot catalog.
2. The MVP validates a complete evidence-heavy workflow instead of maximizing agent count.
3. The recommended MVP team is one manager/orchestrator plus Research, Analyst, and Writer/Reporter agents.
4. MVP tools are small and read-first; consequential external writes require human approval.
5. Trust is measured through accepted completion, grounding, reliability, supervision time, approval safety, cost, and diagnosability—not activity or generated content volume.
6. Autonomy is a policy-bounded execution ceiling. MVP centers on Levels 0–2; any Level 3 scope requires evidence.
7. Users receive structured execution metadata and source/action evidence, never hidden chain-of-thought.

## Important architecture decisions

1. Build and validate the runtime before a large agent catalog.
2. Keep Agent, Skill, Tool, Task, and Workflow as distinct versioned concepts.
3. Make execution and failure state explicit, durable, bounded, cancellable, and recoverable.
4. Enforce least privilege and approval at application, context, and tool boundaries; prompts do not grant authority.
5. Use deterministic workflows wherever deterministic logic is sufficient.
6. Treat knowledge, memory, working state, artifacts, telemetry, evaluation data, and secrets as different data categories.
7. Treat queues, caches, retrieval indexes, analytics, and graph views as derived from canonical state.
8. Keep model providers, tools, retrieval, policy, and event sinks behind typed ports where practical.
9. Do not adopt a comprehensive agent framework as the architecture until core runtime needs have been validated.
10. Begin as a modular application and split services only for demonstrated scale, isolation, reliability, or ownership reasons.

## Open questions

The largest unresolved questions are:

- Which persona and workflow are the first commercial beachhead?
- Should orchestration be agentic, deterministic, or hybrid?
- Which language, persistence model, and durable job mechanism best fit Stage 1 requirements?
- How should Workflow graphs, definition activation/versioning, Skills, and handoff messages be represented?
- What retrieval methods are necessary for the MVP corpus?
- Who owns Memory, how is it promoted, and how does it yield to authoritative Knowledge?
- What policy implementation and data-layer tenancy enforcement are sufficient?
- Which integrations and Level 3 actions justify their added risk?

All 27 tracked questions, their evidence needs, and target stages are in [Open Questions](project/OPEN_QUESTIONS.md).

## Biggest risks

Critical/high risks include hallucinated facts or success claims, prompt injection, tool misuse, permission errors, cross-workspace leakage, secret exposure, duplicate side effects, runaway loops/cost, hidden failures, approval replay/fatigue, evaluation blind spots, and unsafe future execution capabilities. Product risks include premature architecture, unnecessary agentification, and failing to reduce active supervision time. The [Risk Register](engineering/RISK_REGISTER.md) records mitigations, detection, and owners.

## Proposed MVP

A user creates a workspace, adds approved company/source material, and submits a research goal with constraints. A manager coordinates Research, Analyst, and Writer/Reporter roles to collect evidence, analyze it, and create a cited brief. The runtime is bounded and produces structured traces, artifacts, costs, and evaluations. External delivery/publication is drafted and requires approval. Success is compared to a manual or simpler single-agent/deterministic baseline.

## Recommended Stage 1

Build only the application foundation and typed domain contracts:

1. Choose the implementation language through a small, evidence-based ADR.
2. Establish repository tooling, formatting, linting, type checking, tests, and CI.
3. Implement opaque IDs, workspace scope, versioned schemas, and deterministic clock/ID ports.
4. Implement pure Goal, Task, Execution, and Execution Step state machines with explicit terminal/failure states.
5. Define command/query, persistence, policy, model, tool, and event ports; implement only in-memory/test adapters needed for domain scenarios.
6. Add deterministic tests for schema compatibility, legal/illegal transitions, concurrency/version guards, and cross-workspace references.
7. Record persistence and module-boundary choices in ADRs when evidence is available.

Stage 1 completion should demonstrate a deterministic, non-AI domain scenario and CI. It must not include an LLM call or claim an Agent Runtime exists.

## Explicitly not implemented

Stage 0 did **not** implement:

- LLM or model-provider calls;
- an Agent Runtime or decision loop;
- Tool execution or external actions;
- Memory or memory promotion;
- RAG, embeddings, or knowledge ingestion/retrieval;
- multi-agent orchestration, delegation, or communication;
- external integrations, MCP, OAuth connectors, or webhooks;
- graph/org visualization;
- application frontend/backend or fake production dashboards.

No Stage 1 work has begun.
