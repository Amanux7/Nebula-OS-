# ADR-009: Replaceable Orchestration and Delegation

## Status

Accepted — Stage 6, 2026-09-04.

## Context

Stages 1–5 provide canonical Goal/Task/TaskAttempt/Execution state, bounded AgentRuns,
controlled Tools, authoritative Knowledge, and governed Memory. The next capability
must coordinate multiple Tasks and eligible agents without turning a planner into a
new authority or a second execution engine. Plans may be deterministic today and
model-proposed later, so validation, version history, limits, and delegation must not
depend on a provider or agent framework.

## Decision

Orchestration is the coordination layer that transforms an active Goal into a bounded
validated Task graph, assigns ready Tasks to eligible AgentDefinitionVersions, invokes
the existing AgentRuntimeService, tracks outcomes, and validates Goal completion.
It is not Agent Runtime, Tool Runtime, Knowledge, Memory, a queue, a UI, or a prompt.

### Replaceable boundaries

- `OrchestrationStrategyPort` receives a minimal typed `OrchestrationRequest` and
  returns an untrusted `PlanProposal` asynchronously.
- `ResearchBriefPlanStrategy` is the deterministic three-Task baseline.
- `FakeOrchestrationStrategy` scripts proposals and failures for offline tests.
- `AgentSelector` is separate from planning. The deterministic adapter checks exact
  published definitions and stable capability/authority requirements.
- `ResultAggregator` performs structural collection only; it does not decide truth.
- `OrchestrationStore` preserves runs, plan versions, materializations, Delegations,
  run links, and audit Events through the existing atomic in-memory boundary.

No live/model-driven planner is implemented. A future adapter must return the same
strict schema and remains subject to identical validation and time bounds.

### Plan domain and validation

One `OrchestrationRun` is a bounded coordination attempt pinned to strategy and policy
versions. Each immutable `PlanVersion` retains the exact proposal, Goal Version,
strategy, Policy, schema Version, and creation time. A separate immutable
`PlanMaterialization` maps `(plan ID, version, planned task ID)` to canonical Task IDs.
This keeps plan meaning immutable and materialization replay idempotent.

`PlannedTask` contains bounded title, acceptance criteria, priority, one
`requires_success` dependency set, and `AgentRequirements`. Validation rejects foreign
scope, inactive/stale Goals, unknown or duplicate dependencies, cycles, excessive DAG
depth, excessive text/tasks/dependencies, unsupported schema, and requirements that no
catalogued agent can satisfy. Goal text and planner output are data and grant no tools,
Knowledge, Memory, or autonomy.

Stage 6 supports a DAG only. Readiness is derived from canonical Task status: a
proposed/ready Task is runnable exactly when all predecessor Tasks are completed.
Ordering is ascending priority, proposal order, then stable Task ID. Independent ready
Tasks remain observable even though the adapter executes synchronously in-process.

### Materialization and replanning

Materialization creates existing Task entities through `DomainService`; it does not
introduce another Task state machine. The same PlanVersion replay returns the original
materialization. Replans append a new PlanVersion under the same plan identity. Stage 6
requires prior planned-task IDs to remain present and reuses their canonical Tasks;
new IDs may add Tasks. Removing/replacing canonical work is deferred because the
current Goal contract requires all its Tasks to complete and has no “superseded Task”
semantics. Completed work is never duplicated.

Replanning is capped at 2 by default. Retry, redelegation, and replan are distinct:
retry creates a new TaskAttempt/Execution with the same exact agent after a failed
AgentRun; redelegation creates a new assignment to another eligible agent; replan
creates a new immutable PlanVersion. History is retained for all three.

### Delegation and authority

`Delegation` is an immutable assignment record, not an AgentRun. It binds exact
workspace, orchestration/plan/version/planned-task/canonical-task lineage and exact
AgentDefinition ID/Version. Started/completed/failed are derived from linked
`DelegationAttempt` and AgentRun records, avoiding a duplicate lifecycle; the only
stored assignment status is assigned (with cancellation reserved).

Agent requirements may request explicit capabilities, Tool IDs, Knowledge source IDs,
Memory scopes, and minimum autonomy. Selection considers only the latest enabled
published version in the same workspace and applies Policy allowlists. Requirements
must be subsets of that definition’s existing grants. Stable selection orders by
active-run count, definition ID, then newest exact Version. Delegation never widens
Tool, Knowledge, Memory, or autonomy authority.

### Execution, results, and completion

Delegated work always creates TaskAttempts and AgentRuns through existing services.
The orchestration execution is reused while active; runtime failure terminates it and
returns the logical Task to ready, after which a retry Execution links to the failed
one. Runtime validation remains authoritative.

`TaskResultReference` identifies exact source Task, TaskAttempt, AgentRun, result
Version, and original references. Only bounded structured findings are copied to a
downstream `SuppliedContext` and labeled `task_result:...`; complete histories are not
copied. Results remain untrusted data and cannot alter downstream permissions.

Goal completion is explicit and deterministic: every required current-plan Task must
have a successful linked AgentRun and canonical completed Task; the existing
`DomainService.satisfy_goal` then independently requires every Goal Task complete.
Partial success is deferred and never reported as success.

### Policy, failure, and cancellation

Default bounds are 8 Tasks, 3 dependencies/Task, DAG depth 5, 4,000 plan characters,
2 replans, 20 coordination iterations, parallel width 3, 12 AgentRuns, 3 failed
attempts, 1 retry/Task, 1 redelegation/Task, and 5 seconds/planner call. Hard maxima are
enforced by the Policy value object. Exhaustion/no-agent/missing-context cases enter an
explicit waiting/escalation state rather than failing the business Goal.

Cancellation prevents new readiness/delegation, cancels pending Tasks and the current
Execution where applicable, and explicitly cancels the Goal and OrchestrationRun.
Existing runtime version/parent checks reject late results; no claim is made that
unknown remote side effects stop.

Minimal Events record orchestration start, proposal/accept/reject/materialization,
delegation/rejection, replan request/completion, and terminal outcomes. Canonical state
is directly stored; this is not event sourcing.

## Alternatives

- **Planner directly creates/runs agents:** rejected because it conflates proposal,
  validation, authority, and execution.
- **One planner prompt selects agents and grants tools:** rejected; selection and
  permissions are deterministic independent gates.
- **New workflow/Task state machine:** rejected; readiness is derived from existing
  canonical Tasks plus plan dependencies.
- **Mutable latest plan:** rejected because it destroys historical interpretation.
- **Free-form agent chat/blackboard:** deferred; bounded Task results are sufficient.
- **LangGraph/CrewAI/AutoGen or message queues:** rejected for the current offline
  requirements; they add lock-in and operational semantics without an evidenced need.
- **Distributed parallel scheduling:** deferred; Stage 6 proves observable readiness
  and width policy synchronously.

## Consequences

- Planning strategy and agent selection can change independently without changing
  core runtime authority.
- Plans are reproducible, bounded, auditable, and safe to replay.
- Delegation is traceable through canonical execution history.
- The deterministic strategy proves contracts, not general planning intelligence.
- Conservative replan identity rules limit structural replacement until Task
  supersession/partial-Goal semantics exist.
- In-memory synchronous execution provides no process-loss recovery or distribution.

## Deferred Questions

- Model-driven planner adapters and calibrated plan-quality evaluation.
- Structural replans that retire/supersede Tasks and partial Goal satisfaction.
- Durable scheduling, leases, timers, process-loss recovery, and true concurrency.
- Human approval/escalation UI and authenticated orchestration principals.
- Free-form agent communication and typed handoffs (Stage 7).
- Load-aware routing beyond the in-process active-run tie-breaker.
- Production persistence, retention, deletion, and audit delivery.
- External write orchestration, compensation, MCP, and graph visualization.
