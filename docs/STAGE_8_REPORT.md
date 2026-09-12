# Stage 8 — Departments, Agent Registry, and Organizational Graph

Verification date: 2026-09-11. Scope: offline, in-process implementation.

## Outcome

PASS. Organization-aware discovery and routing now integrate with canonical
orchestration, communication, and handoffs. Immutable structural versions preserve
historical interpretation; organization only narrows eligibility and never grants
runtime authority. Stage 9 has not been started.

## Stage 7 Baseline

The existing local Stage 7 implementation was inspected and retained. Before Stage 8,
the gate passed: Ruff format check (78 files), Ruff lint, mypy (76 source files),
pytest (331 passed in 5.07s), and git diff --check. These were local results, not
claims about GitHub CI. Existing uncommitted Stage 7 changes remain in the worktree.

## Stage 7 Corrections

No blocking baseline failure was found. Stage 8 tightens handoff candidate resolution
to intersect the original Task requirements with requested recipient requirements and
organizational policy before canonical redelegation. A handoff cannot weaken the Task
or gain privileges by changing its recipient. Existing Stage 7 regression tests pass.

## Organizational Boundary

Workspace remains company identity/scope. Organization is not authorization, a
department is not a permission, a role is not a capability, and a manager is not an
administrator. The organization graph is separate from the Task dependency graph.
The existing runtime, Tool, Knowledge, Memory, communication, and orchestration
policies remain authoritative. No new runtime engine or external infrastructure exists.

## OrganizationGraph

OrganizationGraph holds stable identity, workspace, optimistic revision, and an active
version pointer. OrganizationGraphVersion contains immutable, bounded structural
records. OrganizationService validates whole-version publication and explicit
activation against exact existing agent configurations. Version creation/activation
and their audit records share the in-memory transaction/rollback boundary. Failed
validation or audit persistence leaves prior state intact. There is no mutable draft
repository; host code constructs a candidate and explicitly publishes it.

## Departments

Department has a scoped opaque ID, name, active/disabled status, and bounded untrusted
description. Disabled departments cannot supply eligible registry candidates.
Changes require a new graph version, not mutation of historical structure.

## Org Roles

OrgRole describes responsibility, optionally designating a department lead. It is
not the agent configuration's runtime role and cannot replace its grants. Unknown
role references and spoofed role IDs fail. Escalation discovers a lead destination;
it does not execute work or elevate authority.

## Capability Registry

CapabilityDefinition provides workspace-local typed CapabilityId identity and
active/disabled status. Exact AgentDefinitionVersions reference capability IDs;
publication validates them against the catalog. A disabled capability cannot satisfy
a query requiring it. Legacy Stage 6 string capability labels remain for historical
compatibility, not description-derived authorization. No semantic matching is added.

## Memberships

DepartmentMembership records agent identity, department, role, active/revoked status,
discoverability, and optional UTC effective bounds. The end instant is exclusive.
Queries use the injected clock. Revoked, expired, future, hidden, and disabled-department
memberships cannot supply candidates. Multiple memberships are explicit and bounded.
At most one active lead membership exists per department, conservatively even when
future effective windows do not overlap.

## Reporting Relationships

ReportingRelationship is structural only. Known same-workspace participants, one
manager per subordinate, no self-reporting, acyclicity, and bounded depth are enforced.
There is no reporting-derived permission aggregation or implicit membership.

## Agent Registry

RegisteredAgent stores only an exact existing AgentDefinitionId/version reference.
AgentRegistry resolves canonical RuntimeStore configurations rather than copying
configuration. RegistryQuery filters department, organizational role, and typed
capabilities, with effective/discoverable membership and enabled-definition checks.
Results are immutable and deterministically sorted by ID/version. Unknown filters,
foreign workspace references, and altered snapshots fail explicitly.

## Registry vs AgentSelector

The registry discovers candidates; the existing AgentSelector makes the final choice.
Required department/role/capabilities filter candidates; a preferred department is
tried first with deterministic fallback if no preferred candidate satisfies runtime
requirements. Existing grants, autonomy ceilings, orchestration allowlists, and
active-run-count/ID/version tie-breaking still apply.

## Organization-Aware Orchestration

OrchestrationRun pins an OrganizationSnapshot at start. Plan acceptance, delegation,
replanning, and execution resolve candidates within that version. Execution rechecks
eligibility before a runtime attempt starts. Missing registry wiring fails for pinned
runs. Legacy unpinned runs remain supported only without organization requirements.
Canonical Goal, Task, TaskAttempt, Execution, Delegation, and AgentRun ownership is
unchanged; no parallel organization-owned execution state machine was introduced.

## Cross-Department Delegation

Directional department rules only narrow eligibility. Same-department routes default
to allow, cross-department routes default to deny, and explicit rules override those
defaults. An optional initial source department, dependency-result sources, and prior
assignees constrain delegation. For multiple effective memberships every source/target
pair must allow the route. A second membership cannot bypass a denial.

## Cross-Department Communication

Messages additionally require the pinned organization's message route before existing
Stage 7 participant, exact-version, runtime-role, and reference authorization checks.
An allowed department route cannot disclose a restricted Knowledge pack or transfer
Tool/Knowledge/Memory grants. Delivery remains distinct from consumption.

## Handoffs

Handoff resolution intersects original Task requirements, target requirements, registry
eligibility, and both handoff and delegation department policies. It retains canonical
redelegation and ancestor exclusions. A denied handoff does not terminate the sender.
The Product-to-Research scenario uses preferred Product routing and a Research lead
qualified for both the original analysis and requested research capabilities.

## Manager / Lead Authority

Lead designation enables destination discovery only. Tests execute a real handoff-created
lead AgentRun and prove denied Tool, Knowledge, and Memory access despite the source
subordinate possessing grants. The lead receives no inherited credentials, access
receipts, identity, or permission. Tool denial creates no successful tool invocation.

## Graph Version Pinning

New runs capture the newly activated version; existing runs and replans retain the
original graph and exact registered definition versions. Store guards reject pin
mutation. Membership effective windows are evaluated at use time within the pin.
A v2 membership revocation does not rewrite a v1 run: immediate global revocation of
pinned structural policy remains unresolved. Independent runtime resource revocation
controls are not replaced by this historical graph contract.

## Security

Workspace isolation covers structural records, registry queries, snapshots, activation,
and integration paths. Models/plans/messages have no organization mutation Action or
port. Descriptions are bounded data, never authority. Explicit role/capability IDs
prevent natural-language spoofing. Canonical snapshot comparison rejects forgery.
Host administration is trusted in-process code, not authenticated production identity.

## Limits

| Bound | Default | Hard maximum |
|---|---:|---:|
| Departments | 12 | 32 |
| Roles | 16 | 64 |
| Capabilities | 32 | 128 |
| Memberships, registered agents, reporting edges | 64 each | 256 each |
| Memberships per agent | 3 | 8 |
| Agents per department | 20 | 64 |
| Reporting depth in edges | 5 | 10 |
| Department route rules | 64 | 256 |

Names are limited to 200 characters, department descriptions to 1,000, and capability
lists to ten IDs. Bounds are validated before graph traversal. There is no unbounded
directory scan or graph expansion beyond these bounded snapshots.

## Deterministic Demo

The fictional Aurora Desk fixture includes four departments and five agents. Tests
exercise scoped discovery and selection, a three-Task orchestration through canonical
Goal completion, organization-governed messages and handoffs, Product-to-Research
handoff with original requirements preserved, lead escalation without inherited grants,
and graph v1/v2 history. All use deterministic clocks, IDs, scripted models, and
in-memory stores, with no live provider or external service.

## Tests

The full gate ran on 2026-09-11 after code changes:

| Command | Actual result |
|---|---|
| `python -m ruff format --check .` | 85 files already formatted |
| `python -m ruff check .` | All checks passed |
| `python -m mypy` | Success: no issues found in 83 source files |
| `python -m pytest -q` | 386 passed in 5.63s; zero failures |
| `git diff --check` | Passed, exit 0 |

The 55 new organizational tests cover structural validation and bounds, deterministic
filtering, lifecycle/effective windows, reporting cycles and managers, workspace
isolation, stale revision conflicts, atomic rollback, immutable/exact configuration
pins, all three routing kinds, multiple memberships, original handoff requirements,
restricted references, role spoofing, description injection, and actual runtime
authority denial. The 331-test baseline remains passing. Scripted tests demonstrate
software invariants, not live-model quality or production durability.

## Files Changed

Stage 8 additions:

- `src/agent_company_os/domain/organization_ids.py`
- `src/agent_company_os/domain/organization.py`
- `src/agent_company_os/ports/organization.py`
- `src/agent_company_os/adapters/organization_store.py`
- `src/agent_company_os/application/organization.py`
- `src/agent_company_os/application/organization_serialization.py`
- `tests/test_organization.py`
- `docs/architecture/ADR/ADR-011-departments-agent-registry-and-organizational-graph.md`
- `docs/STAGE_8_REPORT.md`

Existing implementation extended for Stage 8:

- `src/agent_company_os/domain/agent.py`
- `src/agent_company_os/domain/orchestration.py`
- `src/agent_company_os/domain/plan_validation.py`
- `src/agent_company_os/domain/events.py`
- `src/agent_company_os/domain/transitions.py`
- `src/agent_company_os/ports/ids.py`
- `src/agent_company_os/adapters/ids.py`
- `src/agent_company_os/adapters/agent_selector.py`
- `src/agent_company_os/adapters/orchestration_store.py`
- `src/agent_company_os/application/orchestration.py`
- `src/agent_company_os/application/communication.py`
- `src/agent_company_os/application/communication_serialization.py`

Documentation updated:

- `README.md`
- `docs/architecture/DOMAIN_MODEL.md`
- `docs/architecture/SYSTEM_ARCHITECTURE.md`
- `docs/architecture/AGENT_RUNTIME_ARCHITECTURE.md`
- `docs/architecture/DATA_ARCHITECTURE.md`
- `docs/architecture/SECURITY_AND_PERMISSIONS.md`
- `docs/engineering/DEVELOPMENT_ROADMAP.md`
- `docs/engineering/TESTING_STRATEGY.md`
- `docs/engineering/EVALUATION_STRATEGY.md`
- `docs/engineering/OBSERVABILITY_STRATEGY.md`
- `docs/project/GLOSSARY.md`
- `docs/project/OPEN_QUESTIONS.md`

This inventory identifies Stage 8 work, not every difference from Git HEAD. The
pre-existing uncommitted Stage 7 report, ADR-010, communication modules/tests/fixtures,
and runtime/context/model/orchestration regression changes were preserved. Stage 8
also extends the two listed Stage 7 application communication files. No commit, push,
or GitHub review is claimed by this report.

## Architecture Decisions

[ADR-011](architecture/ADR/ADR-011-departments-agent-registry-and-organizational-graph.md)
records whole-version structural ownership, exact configuration references, registry
versus selection, required/preferred routing, conservative multi-membership policy,
historical pinning with live effective-window checks, trusted host mutation, explicit
audit serialization, atomic in-memory activation, and earned-complexity limits.
Earlier accepted ADRs were not rewritten to accommodate implementation convenience.

## Deferred Work

No graph UI/editor, self-organizing/model-created agents, dynamic hiring/firing,
self-promotion, autonomous department creation/restructuring, manager superuser,
Tool/Knowledge/Memory permission inheritance, LDAP, SCIM, graph database, distributed
registry, production identity provider, or Stage 9 governance was added. Durable
storage/recovery, analytics, calibrated model evaluations, production telemetry, and
authenticated organizational administration remain future work.

## Open Questions

- How should immediate revocation affect already pinned organizational policy?
- Which authenticated principals may publish, activate, and approve changes?
- Should matrix organizations select an explicit department context instead of all-pairs routing?
- How should non-overlapping lead windows, version retention, and redaction evolve?
- What durable transaction, recovery, and evaluator evidence is required before production?

These limits do not block the bounded offline Stage 8 scope; they do block claims of
production readiness and broader consequential autonomy.

## Stage 8 Completion Verdict

PASS for the requested deterministic scope. Domain, registry, orchestration,
communication, handoff, authority-isolation, versioning, rollback, bounds, full gate,
documentation, ADR, and report requirements are present. No external infrastructure
or new production authority was introduced. Changes remain local and uncommitted.

## Recommended Stage 9

Recommend **Human Approval, Autonomy Levels, and Consequential Action Governance**.
The current runtime still denies consequential external writes; the next missing
capability is authenticated approval bound to the exact action payload, with expiry,
replay protection, current-policy revalidation, and cancellation/kill controls. Stage 8
provides deterministic routing and identity boundaries that this governance can use.
Durability, evaluation, observability, and recovery hardening remain prerequisites for
production deployment, not reasons to enable external writes early. Stage 9 has not
been implemented.
