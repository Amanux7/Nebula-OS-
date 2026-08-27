# MVP Scope

## MVP

The MVP validates whether users can trust and benefit from a small, governed agent team on one evidence-heavy workflow.

### Product slice

- Workspace and user membership sufficient for isolation and ownership.
- One manager/orchestrator plus three agents: Research, Analyst, and Writer/Reporter.
- Versioned Agent Definitions, Skills, Tool Definitions, Goals, Tasks, and Executions.
- A small, read-first tool registry (for example governed web/source retrieval and internal artifact access); any external write remains approval-gated.
- Basic Company Brain ingestion and retrieval for a constrained set of text/document sources, with provenance and access control.
- Bounded runtime with structured decisions, limits, cancellation, failure states, and deterministic provider doubles.
- Execution traces and artifact outputs.
- Human approval for proposed consequential actions.
- Initial offline evaluations and operational metrics.

### Reference outcome

Given a research goal and approved sources, the system collects evidence, analyzes it, produces a cited brief, and pauses before any external publication or delivery.

### MVP exit criteria

- The reference workflow meets the initial targets in [Success Metrics](SUCCESS_METRICS.md) on a representative fixture set.
- Workspace isolation, policy denial, cancellation, retry/idempotency, and approval binding have automated coverage.
- A user can diagnose every seeded failure from the trace.
- No critical/high unresolved security issue remains in the scoped workflow.

## Post-MVP

- Durable multi-step workflows and scheduling.
- Scoped episodic memory with retention controls.
- Additional read and draft integrations selected from validated demand.
- Department and agent registry management.
- More sophisticated delegation, handoffs, and replay.
- Execution graph and operational dashboards backed by real state.
- Online evaluation sampling and regression comparison.

## Future

- Multiple organization/workspace administration and enterprise identity controls.
- Carefully bounded Level 3 and Level 4 operation for proven use cases.
- Rich multimodal knowledge and voice/transcript sources.
- Agent/skill template exchange after security and compatibility models mature.
- Advanced cost routing, simulation, policy authoring, and organization analytics.
- Broad direct API, MCP, webhook, and OAuth connector ecosystem.

## Out of scope

- A fixed catalog of 20–30 agents or hard-coded org chart.
- Unrestricted credentials, shell, browser, or environment access.
- Unbounded reasoning loops or self-modifying production agents.
- Graph visualization as canonical state.
- Vector search presented as complete memory or Company Brain.
- Mandatory paid/live model calls in regular tests.
- Broad integration coverage before the tool permission model is proven.
- Fake dashboards, fake execution data, or claims of implemented AI behavior.
- Consumer chat replacement, model training, billing platform, mobile/voice clients, or on-premises deployment in the first release.

## Scope change rule

An addition enters MVP only if it is required to deliver, govern, observe, or evaluate the reference workflow. Otherwise it is placed in Post-MVP or Future with an explicit rationale.
