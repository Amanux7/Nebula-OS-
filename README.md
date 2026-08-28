# Agent Company OS

**Current Stage: Stage 0.1 — Architecture Refinement**

Agent Company OS is a working title for a production-oriented platform for operating an AI-native organization. It is intended to coordinate goals, specialized agents, deterministic workflows, governed tools, shared knowledge, human approvals, and auditable execution—without reducing the product to a collection of chatbots.

## Why it exists

Current AI assistants are often isolated, difficult to govern, weakly observable, and hard to reuse. Agent Company OS aims to provide explicit organizational, runtime, permission, and evaluation structures so that useful autonomy can be introduced safely.

## High-level architecture

The conceptual system separates the experience and application layers from orchestration, agent and tool runtimes, knowledge and memory, durable state, policy enforcement, observability, and evaluation. The architecture is technology-agnostic at this stage. See [System Architecture](docs/architecture/SYSTEM_ARCHITECTURE.md) and [Domain Model](docs/architecture/DOMAIN_MODEL.md).

## Documentation map

- [Product requirements](docs/product/PRD.md), [personas](docs/product/PERSONAS.md), [user journeys](docs/product/USER_JOURNEYS.md), [MVP scope](docs/product/MVP_SCOPE.md), and [success metrics](docs/product/SUCCESS_METRICS.md)
- [Architecture](docs/architecture/SYSTEM_ARCHITECTURE.md), [runtime](docs/architecture/AGENT_RUNTIME_ARCHITECTURE.md), [data](docs/architecture/DATA_ARCHITECTURE.md), [security](docs/architecture/SECURITY_AND_PERMISSIONS.md), [ADR-001](docs/architecture/ADR/ADR-001-architecture-principles.md), [ADR-002](docs/architecture/ADR/ADR-002-execution-domain-semantics.md), and [ADR-003](docs/architecture/ADR/ADR-003-agent-definition-and-runtime-identity.md)
- [Engineering principles](docs/engineering/ENGINEERING_PRINCIPLES.md), [roadmap](docs/engineering/DEVELOPMENT_ROADMAP.md), [testing](docs/engineering/TESTING_STRATEGY.md), [evaluation](docs/engineering/EVALUATION_STRATEGY.md), [observability](docs/engineering/OBSERVABILITY_STRATEGY.md), and [risk register](docs/engineering/RISK_REGISTER.md)
- [Glossary](docs/project/GLOSSARY.md), [assumptions](docs/project/ASSUMPTIONS.md), [open questions](docs/project/OPEN_QUESTIONS.md), [Stage 0 report](docs/STAGE_0_REPORT.md), and [Stage 0.1 refinement report](docs/STAGE_0_1_REFINEMENT_REPORT.md)

## Development philosophy

Build trust and visibility before autonomy. Keep state explicit, boundaries typed, permissions least-privileged, model outputs validated, and deterministic work deterministic. Treat failure, approval, auditability, and evaluation as runtime concerns rather than UI afterthoughts.

## Current status and next milestone

Stage 0 defined the product and engineering foundation. Stage 0.1 refines execution semantics, AgentDefinition versioning, runtime identity, Goal/Task boundaries, the orchestration seam, Memory boundaries, and minimal-infrastructure constraints. No application, LLM integration, runtime, Tool execution, RAG, or dashboard has been implemented. The next milestone is **Stage 1: Deterministic Domain Foundation**, as specified in the [development roadmap](docs/engineering/DEVELOPMENT_ROADMAP.md).
