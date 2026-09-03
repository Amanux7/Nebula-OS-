# Development Roadmap

## Delivery rules

Stages are capability gates, not calendar estimates. A later stage begins only when the prior stage's core contracts and tests are credible. Findings may revise later scope through ADRs; no stage is permission to add all candidate infrastructure.

## Stage 0 — Product and architecture foundation

- **Objective:** align product scope, language, boundaries, risks, and sequencing.
- **Build:** PRD, conceptual architecture, domain model, security model, strategies, roadmap, glossary, and decision record.
- **Do not build:** application code, LLM calls, runtime, integrations, RAG, or dashboards.
- **Tests required:** document inventory, link/diagram syntax checks, terminology/contradiction review.
- **Completion criteria:** requested artifacts exist, MVP and non-goals are explicit, unresolved decisions are recorded.
- **Questions answered:** what problem, objects, principles, MVP slice, major risks, and next milestone.

## Stage 0.1 — Architecture refinement

- **Objective:** remove ambiguity from execution attempts, runtime records, Agent configuration identity, planning seams, Memory boundaries, and Stage 1 infrastructure scope.
- **Build:** documentation decisions, explicit state models/invariants, ADR-002, ADR-003, and the refinement report.
- **Do not build:** application code, AI/runtime behavior, Tool execution, Knowledge/Memory systems, orchestration, or infrastructure.
- **Tests required:** terminology, link, diagram-fence, lifecycle/invariant, scope, and contradiction checks across documentation.
- **Completion criteria:** ExecutionStep is removed from canonical vocabulary; TaskAttempt and AgentDefinitionVersion semantics are explicit; AgentRun persistence and planning strategy remain appropriately deferred; Stage 1 scope is deterministic and minimal.
- **Questions answered:** attempt boundaries, current state versus transition/Event history, historical Agent configuration binding, and replaceable planning boundary.

## Stage 1 — Deterministic Domain Foundation

- **Verified status (2026-09-03):** cleanup gate passed, 51 tests and formatting/lint/type checks. See [Stage 1 report](../STAGE_1_REPORT.md); this is the actual verification date, not a historical CI claim.

- **Objective:** create a minimal executable domain foundation that proves software guarantees without AI behavior.
- **Build:** Workspace identity/scope, opaque IDs, versioned schemas, Goal lifecycle, Task lifecycle, TaskAttempt lifecycle, Execution lifecycle, explicit StateTransition history, a minimal versioned Event/audit envelope, deterministic clock/ID ports, optimistic concurrency/version guards, typed command/query boundaries, in-memory/test persistence adapters, workspace-isolation invariants, repository tooling, and CI. AgentDefinition and AgentDefinitionVersion may exist only as minimal type/reference concepts needed to prove immutable historical binding.
- **Do not build:** LLM calls, model providers, AgentRun/reasoning loop, Action/Observation runtime families, Tool execution, RAG, embeddings, Memory system or generic memory fields, multi-agent communication, orchestration implementation, MCP, production background queues/workers, graph UI, autonomous actions, production database, event sourcing, CQRS, microservices, or agent frameworks.
- **Tests required:** schema compatibility, complete legal/illegal state transition tables, Goal/Task/TaskAttempt/Execution terminal-state behavior, retry lineage, cancellation distinct from failure, optimistic concurrency conflicts, cross-workspace references, definition-version binding, Event/StateTransition append behavior, and serialization. Tests use deterministic clock/ID ports and in-memory adapters.
- **Completion criteria:** domain scenarios run deterministically; illegal transitions, terminal-state reopening, stale-version writes, and cross-workspace references fail; retry creates a new TaskAttempt/Execution where required; no state alone claims an external side effect; CI passes without network or infrastructure services.
- **Questions answered:** primary implementation language, project/module boundaries, validation approach, canonical lifecycle representation, concurrency guard contract, and minimum schema-versioning strategy. A database or infrastructure choice is not required; if introduced, it requires a separate evidence-based ADR.

## Stage 2 — Single-agent runtime

- **Implemented status (2026-09-03):** bounded single-agent runtime and Research Brief Agent validated with scripted model fixtures; [Stage 2 report](../STAGE_2_REPORT.md) records exact checks and limitations. No live-model capability is claimed.

- **Objective:** prove one bounded reasoning loop against a fake model.
- **Build:** AgentDefinition/AgentDefinitionVersion behavior configuration, AgentRun and AgentInvocation contracts, context contract, initial typed model Action/Observation families, structured decision schema, model port and scripted double, limits, cancellation, terminal evaluation, and traces.
- **Do not build:** live model required in CI, external tools, multi-agent delegation, durable workflow engine.
- **Tests required:** malformed/refused/timed-out model output, limit exhaustion, no-progress loop, cancellation race, context overflow, deterministic golden scenarios.
- **Completion criteria:** a scripted AgentRun completes, fails with a categorized timeout where applicable, cancels, and escalates correctly with reproducible TaskAttempt and Execution traces bound to an exact AgentDefinitionVersion.
- **Questions answered:** minimum runtime contract, decision types, error taxonomy, trace granularity, whether a focused library helps.

## Stage 3 — Tool Runtime

- **Implemented status (2026-09-03):** offline read-only tool gate passed. [Stage 3 report](../STAGE_3_REPORT.md) records exact local checks; no live-tool or production guarantee is claimed.
- **Objective:** authorize, bound, execute, and audit typed capabilities outside model reasoning.
- **Build:** ToolDefinition/immutable ToolVersion, exact registry/grants, ToolInvocation/ToolReceipt, ToolExecutor/FakeToolExecutor, call_tool, two read-only fixture lookups, strict schemas, time/call/byte bounds, no-retry policy seam, Action-identity idempotency, claim/revalidation/atomic reconciliation, bounded Observations, receipt-grounded completion, and explicit audit export.
- **Do not build:** external writes, approval engine, secret/connection system, real network dependency, shell/browser/filesystem tools, MCP, OAuth, RAG, Memory, multi-agent runtime, or production infrastructure.
- **Tests required:** successful use/continuation; denied, unknown, disabled, foreign, and unpublished tools; invalid inputs/outputs; timeout; recovery; budgets; duplicate/stale calls; cancellation; immutable version history; forged/foreign evidence; injection; byte/context limits; claim/result rollback.
- **Completion criteria:** only granted read-only tools execute; same invocation is not executed twice; receipt outcomes and trust are explicit; all checks pass offline. This does not establish exactly-once external writes.
- **Questions answered:** tool identity versus version, permission declaration, executor port, bounded evidence, local idempotency and failure policy. Production isolation, connections, durable recovery, and approval remain deferred under ADR-006.

## Stage 4 — Knowledge / Company Brain

- **Implemented status (2026-09-03):** offline Company Brain gate passed: 206 tests, including 51 knowledge cases. See [Stage 4 report](../STAGE_4_REPORT.md) and [ADR-007](../architecture/ADR/ADR-007-company-brain-and-knowledge-retrieval.md).
- **Objective:** provide source-aware, authorized context for the reference workflow.
- **Built:** text/Markdown/typed-fact ingestion, immutable source versions/chunks, direct source grants, disablement, lexical-overlap retrieval, bounded EvidencePacks, exact structured-fact grounding, shared atomic in-memory adapter, and host-driven retrieval/runtime integration.
- **Not built:** embeddings, live providers, generic document parsing, memory, automatic retrieval planning, semantic entailment, infrastructure, or hard deletion.
- **Tests passed:** A–T source/history/scope/disablement/conflict/ranking/size/provenance/injection/context/rollback scenarios; combined tool and knowledge use. Scripted fixtures are not live-model quality scores.
- **Completion criteria:** the requested deterministic baseline and disablement/access gate passes. ADR-007 explicitly defers the former broad semantic-quality and deletion-propagation targets pending real requirements.
- **Questions answered:** lexical baseline, immutable provenance/pack model, latest active retrieval versus exact historical versions, direct source allowlists, internal capability seam. Production freshness and retention remain open.

## Stage 5 — Agent state and memory

- **Objective:** separate working state from deliberately retained experience.
- **Build:** Memory Entry schema, scope, promotion/review policy, confidence/provenance, expiry/supersession, retrieval limits.
- **Do not build:** automatic retention of every conversation, global personality memory, vector search as memory.
- **Tests required:** scope isolation, stale/superseded memory, retention/deletion, poisoning/prompt injection, conflict with authoritative knowledge.
- **Completion criteria:** memory improves selected eval cases without violating isolation or freshness guardrails.
- **Questions answered:** ownership, promotion, retention, conflict resolution, types of memory worth retaining.

## Stage 6 — Orchestration and delegation

- **Objective:** convert Goals into bounded Tasks and coordinate the MVP agent team.
- **Build:** replaceable PlanningPort/Structured Plan contract, deterministic and agentic/hybrid strategy adapters as justified, domain validation of proposed plans, dependency scheduling, eligibility selection, budgets, progress aggregation, handoff and escalation records.
- **Do not build:** unlimited recursive delegation, mandatory supervisor for every workflow, departments UI.
- **Tests required:** cyclic dependency/handoff, partial failure, budget allocation, cancellation propagation, poor-plan fixtures, deterministic direct-workflow path.
- **Completion criteria:** at least two planning strategies can drive the same Goal/Task/TaskAttempt/Execution machinery; the chosen manager coordinates Research, Analyst, and Writer/Reporter on reference cases within bounds.
- **Questions answered:** orchestrator identity, planning representation, routing criteria, task ownership.

## Stage 7 — Multi-agent communication

- **Objective:** make agent collaboration typed, scoped, and inspectable.
- **Build:** message/handoff envelope, context/reference transfer, recipient validation, correlation and loop prevention, shared-artifact conventions.
- **Do not build:** unbounded group chat, invisible shared context, peer authority escalation.
- **Tests required:** unauthorized context transfer, duplicate/out-of-order messages, cyclic handoffs, version mismatch, delivery failure.
- **Completion criteria:** agents collaborate without shared process memory and every handoff is attributable.
- **Questions answered:** message persistence, delivery semantics, conversation versus task linkage.

## Stage 8 — Departments and agent registry

- **Objective:** organize proven capabilities without hard-coded company structure.
- **Build:** Department grouping, discoverable registry, version activation/deprecation, capability metadata, policy defaults, compatibility validation.
- **Do not build:** arbitrary agent quantity, marketplace economics, graph as truth.
- **Tests required:** activation/version resolution, policy inheritance/narrowing, archive behavior, capability selection.
- **Completion criteria:** operators can safely discover and govern active definitions and departments.
- **Questions answered:** hierarchy constraints, lifecycle UX, template portability.

## Stage 9 — Human approval and autonomy policies

- **Objective:** productionize human control and narrowly bounded execution.
- **Build:** Approval Request lifecycle, payload binding, eligible approvers, expiry, revalidation, autonomy levels, policy simulator, kill controls.
- **Do not build:** broad Level 4 autonomy, trust-by-reputation, approval that changes only UI state.
- **Tests required:** tampering/replay, stale policy/data, revocation race, approver separation, kill latency, risk-class matrix.
- **Completion criteria:** all consequential reference actions are enforced end to end with auditable decisions.
- **Questions answered:** policy engine complexity, approval granularity, multi-party needs, safe Level 3 candidates.

## Stage 10 — Execution graph and observability UI

- **Objective:** make real runtime state understandable and operable.
- **Build:** trace query model, timeline/graph projections, logs/metrics/traces correlation, failure drill-down, artifact and approval views, redaction.
- **Do not build:** hard-coded demo graph, chain-of-thought viewer, canonical edits in visualization.
- **Tests required:** projection consistency, redaction, accessibility, large trace performance, incomplete telemetry.
- **Completion criteria:** users diagnose all seeded incidents and views match canonical records.
- **Questions answered:** projection/store needs, retention, operator versus end-user views.

## Stage 11 — Evaluations and reliability hardening

- **Objective:** prevent behavioral regressions and quantify readiness.
- **Build:** versioned datasets/evaluators, offline runner, sampled online evaluation, comparison gates, adversarial suites, reliability/load/chaos work.
- **Do not build:** one opaque quality score or live-model dependency for every test.
- **Tests required:** evaluator validity/repeatability, dataset leakage, regression gates, provider outages, recovery/load tests.
- **Completion criteria:** MVP targets have evidence, critical regressions block promotion, failure budgets are understood.
- **Questions answered:** release thresholds, sampling, human calibration, provider/model routing.

## Stage 12 — External integrations

- **Objective:** add integrations driven by validated workflows.
- **Build:** OAuth/connection lifecycle, selected direct API/webhook/MCP adapters, connector conformance kit, reconciliation and rate handling.
- **Do not build:** indiscriminate connector breadth, bypass of Tool Runtime, permanent broad tokens.
- **Tests required:** sandbox contract, scope/revocation, webhook authenticity/replay, outage/rate limits, schema drift, destructive-action approval.
- **Completion criteria:** selected integrations meet security/reliability SLOs and have operator runbooks.
- **Questions answered:** direct API versus MCP per integration, connector isolation and maintenance ownership.

## Stage 13 — Production deployment and hardening

- **Objective:** operate the validated product safely for real users.
- **Build:** environment/deployment architecture, migrations, backups/restores, DR, SLOs/alerts, incident response, capacity/cost controls, security review, privacy/retention operations.
- **Do not build:** premature global scale, unsupported compliance claims, automatic autonomy expansion.
- **Tests required:** restore and rollback drills, load/soak, failover, penetration/security tests, runbook exercises, data deletion verification.
- **Completion criteria:** production readiness review passes with owners, SLOs, runbooks, monitored guardrails, and rollback.
- **Questions answered:** hosting topology, regions, worker scaling, recovery objectives, operational ownership.

## Immediate next milestone

Stage 4 provides a bounded authorized retrieval baseline and immutable source evidence.
The next proposed milestone is Stage 5: governed state and Memory, beginning with
ownership, promotion/review, expiry, retention, and conflict-policy decisions.
Stage 5 is not started automatically. Live-provider answer quality, durable storage,
production readiness, and external write capability are not implied by this gate.
