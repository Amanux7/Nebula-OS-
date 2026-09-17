# Stage 10 — Durable Recovery and Audit Foundations

Date: 2026-09-17. **Completion verdict: PASS for the requested local, deterministic,
offline Stage 10 scope.** This replaces the incomplete checkpoint. It is not
production-readiness or distributed exactly-once certification.

## Outcome and baseline

Canonical services now use a real SQLite adapter in integration tests, not merely
schema/codec scaffolding. In-memory adapters remain for fast tests.

The recorded Stage 9 baseline was 444 passing tests. An earlier continuation
checkpoint passed 480. On the September 17 resumption the saved working tree passed
511 tests, formatting/lint, and mypy for 103 source files. The final suite passes
**514 tests: all 444 previous regressions plus 70 Stage 10 cases**.

Continuation fixes addressed DelegationAttempt workspace binding, nested rollback,
persisted identity/lineage/audit-subject validation, preservation of disabled Tool
policy across versions, command-wide transactions, and crash-safe orchestration
child-result accounting. No unrelated baseline or landing-page work was changed.

## Storage, migrations, codec and durability classification

ADR-013 selects standard-library SQLite for the smallest offline proof of
transactions, foreign keys, unique identities, SQL conditional updates, restart
reopening and audit queries. No ORM, server or runtime dependency was added.

Explicit 001_domain.sql and 002_runtime.sql migrations record checksummed versions.
Bootstrap, apply-once, sequencing, upgrade, reopen, foreign-key enablement, commit
and rollback are tested. Opening never creates or upgrades canonical tables.
Domain records retain scoped identity, version, status, timestamps and parent
references. Runtime collections retain typed keys, schema/entity versions, SQL CAS
revisions, workspace, retention and explicit JSON payloads.

The allowlisted codec rejects invalid/duplicate JSON fields, unknown type/schema,
missing/extra fields, invalid enums and primitive type confusion. Reopen also checks
row/payload identity, parent columns, workspace links, exact definition snapshots,
receipt/invocation and approval claim bindings, and audit subjects. No pickle,
input-directed executable imports, silently repaired or skipped canonical records.

| Class | Canonical coverage surviving true reopen |
|---|---|
| Safety-critical domain/runtime | Workspace, Goal, Task, TaskAttempt, Execution, AgentDefinitionVersion, AgentRun, working state, counters, deadline, Actions and Observations |
| Authorization/effects | ActionIntent, request, decisions/reviewer, exact fingerprint/policy, expiry, revocation/cancellation, reservation/consumption, Tool registration/enablement, invocation and receipt/certainty |
| Coordination | OrchestrationRun, PlanVersion, materialization, Delegations/attempts/result references, OrganizationGraph versions and active pointer |
| Historical content/provenance | Knowledge sources/versions/content/chunks/EvidencePacks; Memory candidates/review/entries/lifecycle/context packs; threads/messages/handoffs |
| Audit | Events and StateTransitions are append-only history; directly stored entity state remains canonical |
| Rebuildable | Lexical/directory/audit/metric projections are not authorization truth |
| Ephemeral | Live models/executors, locks and transport objects are explicitly rebound, never deserialized |

## Shared transactions, optimistic concurrency and worker claims

SqliteStoreGroup owns one connection across all canonical adapters. Typed service
guards remain in force. The outer unit of work loads current state under BEGIN
IMMEDIATE, validates/mutates, writes changed rows, and commits. Nested immutable
container snapshots restore nested changes when exceptions are caught.
DomainService includes prerequisite reads and writes in that same boundary.

Domain updates use SQL version predicates; runtime rows use SQL revision predicates.
Exactly one row must change. Serialization supplements expected-version checks,
rather than replacing them. Separate connections prove stale-version rejection.
Two worker/service instances competing for the same approval resume produce one
winner, one invocation, one receipt, one consumed approval and one fixture effect.

No leases or automatic claim takeover were added. ToolInvocation plus governed
intent/approval reservation is a one-way durable claim. A lost worker or elapsed
deadline does not establish non-execution.

## Dispatch and crash windows

The Tool Runtime commits AgentRun claim state, ToolInvocation, approval reservation
and authorization audit before executor I/O. No canonical transaction is held
across execution or remote status lookup. Receipt/consumption persistence and local
parent reconciliation are separately recoverable.

| Window | Recovered behavior |
|---|---|
| A: before claim commit | No durable invocation, reservation or effect. Valid approval remains; explicit normal resume revalidates and may execute. |
| B: claim committed, before executor | Claim without receipt is ambiguous; lookup/review, never blind write retry. |
| C: remote effect before receipt | Same local ambiguity. Known remote success/failure creates receipt evidence without dispatch; unknown remains blocked. |
| D: receipt before parent repair | Reuse the exact receipt and repair local bookkeeping idempotently; do not execute again. |

RecoveryService classifies approvals, active/waiting runs, claims without receipts,
receipts needing repair, attempts, executions and orchestration. It calls neither
a model nor a write executor. Existing unknown receipts remain historical evidence.

A ToolReceipt alone does not satisfy Task/Goal acceptance. Existing grounded runtime
completion is still required. Expired, changed, cancelled or terminal parents are
not reopened. OrchestrationService.reconcile_child repairs a committed settled child
without model/planning/Tool I/O. Same-child/version repair is atomic and idempotent.
Failure counts derive from canonical children; new execution checks those counts
even when a parent update was lost to a crash.

## Connector capabilities, idempotency and safe retry

The recovery port distinguishes idempotency-key, status-lookup, remote-cancel and
compensation capabilities. Only an offline fixture is supplied.

RecoverableFixtureExecutor persists its remote ledger in a **separate SQLite file**,
outside application transactions. Its stable key binds workspace, existing exact
intent identity (intent:ActionId), invocation and Tool version. Same key/payload
returns the same logical result; a changed payload fails. Lookup distinguishes
never_received, processed_success, processed_failure and unknown.

Unknown is not failure or safe retry. safe_to_retry is evidence eligibility, not
permission, reusable approval, or a reset of a one-use claim. Authoritative
never_received may support a later explicit governed redispatch protocol; automatic
post-claim redispatch is not implemented. Before-claim retry through normal
revalidation is demonstrated. Read-only eligibility is less restrictive but does
not reset claims or budgets. No generic compensation or distributed exactly-once
guarantee is claimed. Database rollback is not external rollback.

## Approval, AgentRun and cross-subsystem recovery

Exact approved payload/context, policy, reviewer and decision history survive.
Rejection, revocation, consumption and expiry remain effective. Restart does not
reset absolute deadlines, iteration/Tool counts, working state or pinned packs.
Unknown outcomes cannot resurrect approval. Tool enablement survives; publication
does not silently re-enable a disabled Tool. Executors require trusted explicit
binding after restart.

The multi-department demo completes one Task, leaves a second AgentRun waiting,
activates graph v2 while the run stays pinned to v1, closes/discards all services,
then reopens. Plans, delegations, completed results, deadlines and budgets match.
The same logical work resumes, the remaining Tasks and Goal complete, and there
are three AgentRuns—not repeated completed work.

Additional tests crash after successful/failed child completion before orchestration
reconciliation and repair exactly once without losing failure accounting.
Knowledge and Memory retrieval are reconstructed from canonical state, not retained
indexes. Organization and Communication/Handoff scenarios compare exact reopened
records and lineage.

## Audit, redaction, retention and observability

AuditQueryService requires workspace scope for Goal/Task/AgentRun/ActionIntent
timelines, Task approvals, Execution invocations and structured
Goal → Task → TaskAttempt → AgentRun → intent/approval → invocation → receipt traces.
Supplying the orchestration store adds plan/delegation history. Additional event
sources are composed explicitly; no user-supplied SQL is exposed.

Timelines sort by timestamp then EventId, remain identical after reopen, reject
foreign subjects and expose bounded IDs/digests/status/reason codes. Exact messages,
arguments, source content and human free-text reasons are omitted. Tests check that
the fixture message is absent from both the timeline and generic runtime Events.

Retention classification is stored for operational, audit and sensitive collections;
ephemeral live objects are not persisted. ContentTombstone is a future unavailable-
content model, not an enabled deletion job or legal-compliance claim.

Recovery Events make detection, lookup, reconciled receipt and parent repair visible.
Reliability snapshots rebuild bounded detected-case, unknown, reconciliation, review,
retry-candidate, blocked-unknown-decision, incomplete-run and stale-claim counts.
Candidates are not executed retries. Timeline count/latency are process-local derived
telemetry, not authorization state. No telemetry backend is installed.

## Fault injection and restart demonstrations

Tests cover all four crash windows, state/audit/before-commit failures, failures
during receipt reconciliation, remote success/failure/unknown, stale deadlines,
cancelled parents, nested rollback and independent-connection contention.

A separate Python subprocess calls os._exit(73) immediately after its independent
remote commit. No application finally/close handler runs. Fresh services reopen,
lookup success, save the receipt, consume approval and repair the parent without
dispatch. Other restart tests close connections and release captured factories
before constructing new service graphs.

These prove deterministic software/process-crash behavior—not physical power loss,
storage-device durability, distributed consensus, production restore or load SLOs.

## Actual final quality gate

Commands used the repository virtual-environment Python.

| Check | Actual result |
|---|---|
| python -m ruff format --check . | 150 files already formatted |
| python -m ruff check . | All checks passed |
| python -m mypy | Success: no issues found in 103 source files |
| python -m pytest -q | 514 passed in 26.22s; 0 failed |
| git diff --check | Exit 0; informational LF-to-CRLF warnings only |

Stage 10 cases: foundation 18, SQLite contracts 9, recovery 12, subsystem restart 10,
audit/security 11, and storage/remote faults 10. Total 70; all 444 earlier tests remain.

## Files added or changed in this continuation

Documentation:

- README.md
- docs/STAGE_10_REPORT.md
- docs/architecture/ADR/ADR-013-durable-state-recovery-and-audit.md
- docs/architecture/AGENT_RUNTIME_ARCHITECTURE.md
- docs/architecture/DATA_ARCHITECTURE.md
- docs/architecture/DOMAIN_MODEL.md
- docs/architecture/SECURITY_AND_PERMISSIONS.md
- docs/architecture/SYSTEM_ARCHITECTURE.md
- docs/engineering/DEVELOPMENT_ROADMAP.md
- docs/engineering/EVALUATION_STRATEGY.md
- docs/engineering/OBSERVABILITY_STRATEGY.md
- docs/engineering/TESTING_STRATEGY.md
- docs/project/GLOSSARY.md
- docs/project/OPEN_QUESTIONS.md

Code, under src/agent_company_os/:

- adapters/durable_codec.py
- adapters/in_memory.py
- adapters/orchestration_store.py
- adapters/recoverable_fixture.py
- adapters/sqlite_store.py
- application/audit.py (new)
- application/orchestration.py
- application/recovery.py
- application/service.py
- domain/events.py
- domain/tools.py
- ports/orchestration.py
- ports/store.py

Tests:

- tests/test_durable_foundation.py
- tests/test_recovery.py
- tests/test_sqlite_store.py
- tests/test_durable_audit_security.py (new)
- tests/test_durable_faults.py (new)
- tests/test_durable_subsystems.py (new)
- tests/fixtures/recovery_crash_worker.py (new)

Existing checkpoint work reused: adapters/sqlite_database.py,
adapters/migrations/001_domain.sql, 002_runtime.sql, fixture_remote.sql,
domain/recovery.py and ports/recovery.py. Earlier checkpoint changes to Tool Runtime,
governance and runtime-store ports are included in the verified implementation.

## Limits and open questions

- Trusted local filesystem and host composition; no authenticated recovery service,
  encryption, signed history or hostile-admin tamper protection.
- Bounded full-record reads/validation per outer transaction, not a large-corpus
  adapter. Pagination, load/soak and physical power-loss behavior remain unmeasured.
- Failed-worker quiescence is an operator precondition. No leases, fencing,
  distributed ownership, automatic takeover or remote cancellation.
- No automatic post-claim redispatch, guessed model replay, generic compensation,
  or rewriting of an existing unknown receipt. These need explicit later contracts.
- Coordinated application/remote restores and stale-backup authority resurrection
  need a production restore runbook and evidence.
- Retention periods, governed deletion/backup propagation and legal compliance are
  unresolved. Sensitive canonical payloads still need filesystem protection.
- Services must be deliberately composed into a host application. No HTTP platform,
  dashboard, approval UI or fake local preview was built or launched.

No real Gmail/Slack/payment/CRM/database-write integration, MCP, queue, scheduler,
broker, worker fleet, new intelligence or new autonomy was added. The unrelated
landing page is preserved. No commit or push was performed in this continuation.

## Completion verdict and recommended next action

**PASS — Stage 10 local/offline gate.** Canonical services use SQLite; exact
authorization, claims, receipts and cross-subsystem state survive; unknown writes
are not blindly retried; known outcomes reconcile without duplicate fixture effects;
parent repair is idempotent; scoped audit queries and the full quality gate pass.

Recommend a separately scoped Stage 11 for reliability/inspection hardening:
authenticated operator contracts, coordinated restore drills, measured query/load
behavior and a read-only local inspection interface over canonical services.
The landing page must not be presented as that interface.

Stage 11 has not started. Stop after Stage 10.
