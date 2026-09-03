# ADR-004: Primary Backend and Domain Implementation Language

- **Status:** Accepted
- **Date:** 2026-08-29
- **Scope:** Stage 1 primary backend/domain implementation

## Context

Stage 1 needs one language for a small deterministic domain core with differentiated identifiers, immutable value objects, explicit state machines, typed ports, in-memory adapters, serialization, tests, linting, formatting, and static analysis. It does not need an API server, background worker, model provider, Agent framework, database, or frontend.

The realistic candidates are Python and TypeScript. Both are mature, portable, support future APIs/background work, and can integrate with future AI systems. The decision should optimize current domain correctness and maintainability without creating a polyglot backend.

The available development environment provides Python 3.13.6 and Node.js 22.18.0. The local npm installation is currently incomplete, while the Python runtime and package installer are operational. Environment availability is supporting evidence, not the sole architectural reason.

## Decision

Use **Python 3.13** as the primary backend and domain language for Stage 1.

Use:

- standard-library frozen dataclasses, enums, and Protocols for domain and port contracts;
- explicit differentiated identifier value objects rather than untyped strings;
- pytest for deterministic tests;
- mypy in strict mode for static type checking;
- Ruff for formatting and linting;
- a `src/` package layout with domain, application, ports, and adapters modules;
- a single `pyproject.toml` as the project/tool configuration source.

Stage 1 will have no runtime dependency beyond the Python standard library. Development tools are the only package dependencies.

## Alternatives

### TypeScript

TypeScript provides strong structural typing, discriminated unions, excellent JSON/API ergonomics, and potential contract sharing with a future web UI. It is a credible future client/UI language and could support the backend.

It was not selected for Stage 1 because Python expresses the required immutable domain model and Protocol-based ports with less build configuration, has a mature testing/type/lint toolchain, aligns with likely future evaluation/AI engineering work without requiring an AI framework, and is healthy in the current environment. The broken local npm installation would add setup risk without improving the domain proof. This decision does not select a frontend language.

### Python and TypeScript backend split

A polyglot split could optimize different future components, but Stage 1 has no component boundary that justifies duplicated toolchains, serialization contracts, or deployment concerns. Rejected for Stage 1.

### Python without static type checking

This would reduce tooling but weaken differentiated identifiers, port contracts, and refactoring guarantees central to Stage 1. Rejected.

## Consequences

### Positive

- The domain foundation stays small and uses standard language features.
- pytest, mypy, and Ruff provide deterministic and CI-friendly quality gates.
- Protocols keep adapters replaceable without framework inheritance.
- Python remains compatible with future API, job, evaluation, and AI ecosystems while Stage 1 contains no AI dependency.
- A single backend language and tool configuration reduce operational surface.

### Negative

- Python's type guarantees are static-tool dependent and not enforced by the runtime alone.
- Distinct ID types and explicit serialization require deliberate code rather than relying on plain dictionaries.
- A future TypeScript UI will require generated or separately verified API contracts rather than importing backend types directly.
- Python concurrency/performance characteristics may require later evidence-based design for execution workers; Stage 1 does not decide that architecture.

### Follow-up

Revisit the backend language only if measured runtime, deployment, staffing, or interoperability constraints materially invalidate this decision. Add frameworks or infrastructure through separate ADRs when a roadmap requirement demonstrates need.
