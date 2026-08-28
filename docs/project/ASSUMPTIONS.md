# Assumptions

Assumptions are working hypotheses, not accepted architecture decisions. Each should be validated or converted into an ADR/requirement when its roadmap stage needs it.

| ID | Assumption | Why it is reasonable now | Validation / trigger |
|---|---|---|---|
| A-001 | The initial application can optimize for a single organization while every tenant-owned object remains workspace-scoped. | Limits product complexity without blocking isolation. | Stage 1 domain and isolation tests; early customer interviews. |
| A-002 | Cloud deployment is expected later, but local deterministic development is required. | Integrations/workers favor cloud operation; reliable development cannot depend on cloud services. | Stage 1 tooling and Stage 13 deployment ADR. |
| A-003 | Model providers should be replaceable where practical. | Price, capability, policy, and availability will change. | Stage 2 adapter prototype with scripted double and at least one candidate provider contract. |
| A-004 | Tools may eventually use direct APIs, webhooks, OAuth connectors, and MCP. | Integration needs vary and no transport fits all. | Stage 3 tool contract and Stage 12 connector comparisons. |
| A-005 | Human approval remains available at every meaningful autonomy stage. | Trust and consequential actions require intervention paths. | Approval usability/security tests in Stage 9. |
| A-006 | The first valuable workflow is evidence-heavy knowledge work with limited external writes. | It exercises reasoning, retrieval, delegation, artifacts, traces, and approval with lower blast radius. | Persona interviews and MVP pilot. |
| A-007 | One manager plus Research, Analyst, and Writer/Reporter is sufficient to test multi-role value. | Covers distinct workflow responsibilities without artificial agent count. | Stage 6 eval against a simpler single-agent/deterministic baseline. |
| A-008 | Future long-running work needs durable acceptance, cancellation, and recovery semantics. | Provider delays, approvals, and Tool outages outlive request/response cycles. Stage 1 models lifecycle semantics without selecting a queue or worker. | Stage 2 failure tests and later asynchronous execution requirements. |
| A-010 | Stage 1 domain invariants can be proven with in-memory/test persistence adapters. | No current invariant requires a production database, queue, cache, or broker. | Revisit only when a later requirement needs durability, concurrency across processes, or measured query behavior; record any choice in an ADR. |
| A-011 | Agents need read-only or draft capabilities before autonomous writes. | Reduces security and trust risk while runtime controls mature. | MVP usage and approval/correction metrics. |
| A-012 | Authoritative Knowledge, Working State, Conversation History, Episodic Memory, and Semantic Memory require distinct lifecycle and trust semantics even if some later share physical storage. | Source facts, runtime state, interaction records, and retained experience have different provenance/freshness. | Stage 4/5 evaluation and data design; none becomes a generic Stage 1 memory field. |
| A-013 | Deterministic model/tool doubles can cover regular correctness tests. | Runtime and policy invariants should not depend on probabilistic paid calls. | Stage 2 test suite; live eval used only as complementary evidence. |
| A-014 | Users prefer concise structured trace explanations over raw model reasoning. | Structured evidence is safer and more actionable than hidden chain-of-thought. | Stage 10 usability study. |
| A-015 | Early architecture can begin as one application with a typed domain layer and in-memory/test adapters; later it may become a modular application with workers. | Team/scale boundaries are unknown and distributed complexity is costly. Stage 1 requires no production worker or service split. | Revisit upon demonstrated persistence, scaling, isolation, reliability, or ownership pressure. |
| A-016 | Workspaces need configurable retention and deletion even before enterprise compliance features. | Knowledge, memory, artifacts, and telemetry contain sensitive business data. | Stage 1 data contracts and Stage 13 privacy readiness. |

## Assumptions explicitly not made

- That a particular framework, model provider, vector store, workflow engine, or language is best.
- That every workflow requires an orchestrator Agent.
- That more Agents create more product value.
- That vector similarity alone provides adequate retrieval, Memory, or Company Brain behavior.
- That model output is trusted, permissions can be enforced in prompts, or external effects are exactly-once.
- That Level 4 autonomy is required for the MVP.

## Resolved or retired assumptions

- **A-009 (resolved by [ADR-003](../architecture/ADR/ADR-003-agent-definition-and-runtime-identity.md)):** historical runtime records bind an immutable AgentDefinitionVersion and its immutable/transitively versioned behavior configuration. This is now an architectural decision, not an assumption.
