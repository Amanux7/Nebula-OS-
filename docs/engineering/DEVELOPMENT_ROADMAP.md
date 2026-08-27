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

## Stage 1 — Application foundation and typed domain contracts

- **Objective:** create a minimal executable foundation without AI behavior.
- **Build:** repository/tooling, configuration, module boundaries, core IDs/versioned schemas, Goal/Task/Execution state machines, persistence ports with in-memory adapter, command/query contracts, deterministic clocks/IDs, CI.
- **Do not build:** model provider, agent loop, real tools, retrieval, memory, orchestration UI.
- **Tests required:** schema compatibility, state transition tables, tenant-scope invariants, serialization, migration contract if persistence is selected.
- **Completion criteria:** domain scenarios run deterministically; illegal transitions and cross-workspace references fail.
- **Questions answered:** implementation language, module boundaries, validation approach, canonical state representation, initial persistence decision.

## Stage 2 — Single-agent runtime

- **Objective:** prove one bounded reasoning loop against a fake model.
- **Build:** Agent Definition/version, invocation envelope, context contract, structured decision schema, model port and scripted double, limits, cancellation, terminal evaluation, traces.
- **Do not build:** live model required in CI, external tools, multi-agent delegation, durable workflow engine.
- **Tests required:** malformed/refused/timed-out model output, limit exhaustion, no-progress loop, cancellation race, context overflow, deterministic golden scenarios.
- **Completion criteria:** scripted agent completes, fails, times out, and escalates correctly with reproducible traces.
- **Questions answered:** minimum runtime contract, decision types, error taxonomy, trace granularity, whether a focused library helps.

## Stage 3 — Tool system

- **Objective:** execute deterministic capabilities safely through one boundary.
- **Build:** Tool Definition/version, registry, typed adapters, policy hook, secret reference, risk class, timeouts, retries, idempotency, receipts; begin with local/read-only fixtures.
- **Do not build:** broad connector catalog, unrestricted code/shell/browser access, agent-owned credentials.
- **Tests required:** schema/semantic validation, deny/approval paths, transient/permanent/ambiguous failures, replay, rate and size limits, secret redaction.
- **Completion criteria:** no tool bypasses policy; duplicate-effects fixtures remain single-effect; outcome certainty is explicit.
- **Questions answered:** tool contract, permission declaration, adapter isolation, connection model.

## Stage 4 — Knowledge / Company Brain

- **Objective:** provide source-aware, authorized context for the reference workflow.
- **Build:** constrained ingestion, provenance, source version/freshness, access enforcement, retrieval port, full-text/structured baseline, optional semantic experiment, citation contract.
- **Do not build:** claim universal RAG, ingest every format, treat embeddings as truth, memory.
- **Tests required:** ACL leakage, deletion propagation, stale/failed ingestion, citation validity, injection fixtures, retrieval quality baseline.
- **Completion criteria:** reference corpus retrieval meets defined relevance/grounding targets and deletion/access tests.
- **Questions answered:** minimum storage/index approach, retrieval mix, chunk/provenance model, freshness expectations.

## Stage 5 — Agent state and memory

- **Objective:** separate working state from deliberately retained experience.
- **Build:** Memory Entry schema, scope, promotion/review policy, confidence/provenance, expiry/supersession, retrieval limits.
- **Do not build:** automatic retention of every conversation, global personality memory, vector search as memory.
- **Tests required:** scope isolation, stale/superseded memory, retention/deletion, poisoning/prompt injection, conflict with authoritative knowledge.
- **Completion criteria:** memory improves selected eval cases without violating isolation or freshness guardrails.
- **Questions answered:** ownership, promotion, retention, conflict resolution, types of memory worth retaining.

## Stage 6 — Orchestration and delegation

- **Objective:** convert Goals into bounded Tasks and coordinate the MVP agent team.
- **Build:** planning/decomposition contract, dependency scheduling, eligibility selection, budgets, progress aggregation, handoff and escalation records.
- **Do not build:** unlimited recursive delegation, mandatory supervisor for every workflow, departments UI.
- **Tests required:** cyclic dependency/handoff, partial failure, budget allocation, cancellation propagation, poor-plan fixtures, deterministic direct-workflow path.
- **Completion criteria:** manager coordinates Research, Analyst, and Writer/Reporter on reference cases within bounds.
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

Stage 1 should produce no AI feature claims. Its deliverable is a small executable domain core and CI suite that proves versioning, tenant scope, Goal/Task/Execution lifecycles, and adapter boundaries.
