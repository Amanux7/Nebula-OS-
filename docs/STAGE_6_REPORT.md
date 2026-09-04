# Stage 6 Report — Replaceable Orchestration and Delegation

## Outcome

Stage 6 is complete. Agent Company OS can deterministically turn an active Goal into
a bounded validated Task graph, materialize canonical Tasks once, delegate ready Tasks
to eligible exact AgentDefinitionVersions, execute them through the existing
AgentRuntimeService, preserve result lineage, recover within explicit limits, and
complete the Goal only after deterministic checks pass. No Stage 7 communication
capability was implemented.

## Stage 5 Verification

The Stage 5 branch baseline was verified before Stage 6 work:

| Check | Actual result |
|---|---|
| Ruff format | 63 files already formatted |
| Ruff lint | All checks passed |
| mypy | Success: no issues in 61 source files |
| pytest | 246 passed in 2.91s |
| `git diff --check` | Passed |

## Orchestration Definition

Orchestration is the bounded application coordination that proposes and validates a
plan, materializes canonical Tasks, determines dependency readiness, assigns eligible
agents, invokes the established Agent Runtime, records exact outcomes, and requests
Goal completion. It is not planning intelligence, a second execution engine, an
authority source, a queue, or agent-to-agent messaging.

## Orchestration Strategy

`OrchestrationStrategyPort` is asynchronous and accepts a minimal typed request: Goal
identity/version/objective/constraints, a bounded agent capability catalog, and policy.
Its `PlanProposal` output is untrusted. `ResearchBriefPlanStrategy` supplies the
deterministic Research → Analysis → Writing reference workflow.
`FakeOrchestrationStrategy` scripts proposals and failures for offline conformance,
timeout, rejection, and recovery tests. Both pass through identical validation.

No live or model-driven planner was added. A later deterministic, agentic, or hybrid
strategy can replace the adapter without changing Goal/Task/Execution semantics.

## Plan Domain

- `PlanProposal` contains ordered logical `PlannedTask` values and schema version.
- `PlannedTask` contains a stable logical ID, title, acceptance criteria, dependencies,
  priority, required flag, and narrow `AgentRequirements`.
- `PlanVersion` is an immutable accepted proposal bound to workspace, Goal version,
  OrchestrationRun, strategy version, and policy version.
- `PlanMaterialization` records the exact logical-task-to-canonical-Task mapping.

Accepted versions are append-only. A new plan never rewrites prior versions.

## DAG Validation

Deterministic validation rejects a workspace/Goal mismatch, unsupported schema, empty
or oversized plans, duplicate task IDs, unknown or excessive dependencies, cycles,
excessive dependency depth, excessive text, and requirements with no eligible agent.
Dependency readiness is derived from canonical predecessor Task completion.

## Task Materialization

Only an accepted current PlanVersion can materialize. Materialization revalidates the
Goal version and status, creates canonical Tasks through `DomainService`, creates or
reuses an active Execution, and atomically stores the exact mapping. Replaying the same
request returns the existing mapping without creating duplicate Tasks. Replans reuse
canonical Task IDs for retained logical IDs; Stage 6 does not allow a replan to remove
previously accepted logical tasks.

## Delegation

A `Delegation` assigns one ready canonical Task to one exact published
AgentDefinitionVersion and records plan, Task, retry, and redelegation lineage. A
`DelegationAttempt` links the assignment to the exact Execution, TaskAttempt, and
AgentRun created by the existing runtime. A Delegation is not a permission grant or
message, and at most one active assignment exists for a Task.

## Agent Selection

`DeterministicAgentSelector` considers only the latest enabled published definition
version in the same workspace. It requires all requested capabilities, tool grants,
Knowledge sources, Memory scopes, autonomy minimum, and policy allowlists/roles. It
never expands authority. Eligible candidates are ordered by active AgentRun count,
definition ID, then newest version, producing stable selection and load distribution.

## OrchestrationRun

`OrchestrationRun` is the bounded coordinator state for one Goal, strategy, and policy.
Its states are `planning`, `running`, `waiting`, `completed`, `failed`, and `cancelled`.
It carries current Plan/Execution references, replan and run counters, failed-attempt
count, optimistic version, and an explicit escalation reason when waiting.

## Replanning

Replanning is explicit, asynchronous, time-bounded, and limited by policy. It creates a
new immutable PlanVersion after revalidating the active Goal and the full proposal.
Prior plan history and materialized Task mappings remain queryable. Invalid or failed
replans move the run to `waiting` with an actionable reason; they never overwrite the
last accepted plan or mutate canonical state.

## Retry vs Redelegation

A retry creates a new TaskAttempt while preserving the failed TaskAttempt and AgentRun.
Redelegation additionally creates a new Delegation and may bind a different eligible
AgentDefinitionVersion. Each has a separate per-Task limit. Runtime failure returns the
logical Task to `ready`; exhausted failure, run, iteration, retry, or redelegation
budgets move orchestration to `waiting` rather than looping.

## Result Passing

Each successful upstream result is represented by a `TaskResultReference` containing
the exact Task, TaskAttempt, AgentRun, result version, and source references. A dependent
Task receives bounded, explicitly labeled supplied facts only after every predecessor
has a successful exact reference. Result text remains untrusted data: it cannot modify
the AgentDefinitionVersion, tool/Knowledge/Memory grants, autonomy, plan, or policy.

## Result Aggregation

`StructuralResultAggregator` verifies that exactly the required materialized Tasks have
successful result references and returns a deterministic `GoalResultDraft`. It does not
claim semantic output quality, perform model synthesis, or make policy decisions.

## Goal Completion

Orchestration completion requires all materialized canonical Tasks to be `completed`,
a structurally complete result draft, an active Goal, and a successful call to the
existing `DomainService.satisfy_goal`. Task or AgentRun failure alone does not fail the
Goal. Cancellation is distinct and propagates through still-active canonical state.

## Policy / Budgets

The default `OrchestrationPolicy` permits at most 8 Tasks, 3 dependencies per Task,
dependency depth 5, 4,000 plan characters, 2 replans, 20 coordinator iterations,
parallel width 3, 12 AgentRuns, 3 failed attempts, 1 retry per Task, 1 redelegation per
Task, and 5 seconds per planner call. Constructor hard caps prevent configuration from
silently becoming unbounded. Optional exact agent and role allowlists further narrow
selection.

## Security

Cross-workspace plans and delegations are rejected. Stale Goal/run/plan/entity or agent
versions cannot progress. Disabled, mismatched, or under-authorized definitions are
ineligible. Planner-injection fixtures show that instruction-like Task text cannot
bypass validation or authority. Result-poisoning fixtures show that upstream content
cannot grant capabilities or become authoritative Knowledge. Materialization and
delegation rollback tests verify no partial records survive injected persistence faults.

## Tests

The complete deterministic quality gate after implementation:

| Check | Actual result |
|---|---|
| `ruff format --check src tests` | 72 files already formatted |
| `ruff check src tests` | All checks passed |
| `mypy` | Success: no issues in 70 source files |
| `pytest -q --tb=short` | 286 passed in 3.23s |
| `git diff --check` | Passed |

The Stage 6 suite adds 40 tests, including the named A–AC fixture coverage. CI remains
offline and deterministic and requires no providers, network services, or secrets.

## Files Changed

- `README.md`
- `docs/STAGE_6_REPORT.md`
- `docs/architecture/ADR/ADR-009-replaceable-orchestration-and-delegation.md`
- `docs/architecture/AGENT_RUNTIME_ARCHITECTURE.md`
- `docs/architecture/DATA_ARCHITECTURE.md`
- `docs/architecture/DOMAIN_MODEL.md`
- `docs/architecture/SECURITY_AND_PERMISSIONS.md`
- `docs/architecture/SYSTEM_ARCHITECTURE.md`
- `docs/engineering/DEVELOPMENT_ROADMAP.md`
- `docs/engineering/EVALUATION_STRATEGY.md`
- `docs/engineering/OBSERVABILITY_STRATEGY.md`
- `docs/engineering/TESTING_STRATEGY.md`
- `docs/project/GLOSSARY.md`
- `docs/project/OPEN_QUESTIONS.md`
- `src/agent_company_os/adapters/agent_selector.py`
- `src/agent_company_os/adapters/ids.py`
- `src/agent_company_os/adapters/orchestration_store.py`
- `src/agent_company_os/adapters/orchestration_strategy.py`
- `src/agent_company_os/adapters/result_aggregator.py`
- `src/agent_company_os/adapters/runtime_store.py`
- `src/agent_company_os/application/orchestration.py`
- `src/agent_company_os/domain/agent.py`
- `src/agent_company_os/domain/events.py`
- `src/agent_company_os/domain/orchestration.py`
- `src/agent_company_os/domain/plan_validation.py`
- `src/agent_company_os/domain/transitions.py`
- `src/agent_company_os/ports/ids.py`
- `src/agent_company_os/ports/orchestration.py`
- `src/agent_company_os/ports/runtime_store.py`
- `tests/fixtures/agent_eval/orchestration_cases.json`
- `tests/test_orchestration.py`

## Architecture Decisions

[ADR-009](architecture/ADR/ADR-009-replaceable-orchestration-and-delegation.md)
records the replaceable boundary, immutable plan semantics, canonical materialization,
eligibility rules, delegation lineage, bounded recovery, and deferred infrastructure.
Accepted ADR-001 through ADR-008 remain unchanged.

## Deferred Work

- free-form agent chat, agent inboxes, and agent gossip
- agent message bus and typed Stage 7 handoff transport
- durable queues and distributed scheduler
- live planner quality and model-driven/hybrid planning
- production persistence, leases, and process-loss recovery
- human approval UI and production identity/role enforcement
- external write orchestration and autonomous payments
- MCP, browser automation, and external integrations
- graph or organization UI
- self-modifying plans and unbounded replanning/task creation

## Open Questions

- Which measured workflow justifies a model-driven or hybrid planning adapter?
- Should a future PlanVersion be able to supersede/remove materialized Tasks, and what
  canonical Task lifecycle would make that historically honest?
- How should partial Goal satisfaction, optional Tasks, compensation, and semantic
  result quality be represented?
- Which durable worker claim, lease, idempotency, and recovery protocol is required?
- Which Stage 7 messages are necessary beyond Delegation and TaskResultReference?

## Completion Criteria

All mandatory Stage 6 criteria pass: the Stage 5 baseline, replaceable strategy seam,
deterministic strategy, typed/versioned DAG, validation and bounds, idempotent canonical
materialization, deterministic least-authority selection, exact delegation/run/result
lineage, existing Agent Runtime use, dependency blocking, bounded recovery, cancellation,
stale protection, atomic rollback, adversarial fixtures, complete quality gate, ADR-009,
and this report. No free-form agent messaging is claimed.

## Recommended Stage 7

Proceed next with **Stage 7 — Multi-Agent Communication and Handoffs**, using the exact
Delegation and TaskResultReference lineage established here. Stage 7 was not started.
