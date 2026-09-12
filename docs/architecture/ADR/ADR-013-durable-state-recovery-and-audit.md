# ADR-013: Durable State, Recovery, and Audit

## Status

Accepted storage and recovery direction, 2026-09-12. Implementation is in progress;
this ADR is not a claim that the Stage 10 completion gate has passed.
Earlier accepted ADRs remain historical and unchanged.

## Context

The resumed baseline passed 444 tests in 4.60s, Ruff formatting (133 files), Ruff
lint, mypy (88 source files), and `git diff --check`. No blocking baseline defect
was found. All canonical adapters currently keep dictionaries/lists in process.
RuntimeStore shares a domain lock; Knowledge, Memory, Organization, Orchestration,
and Communication add nested rollback snapshots. These boundaries prevent partial
in-process updates but cannot recover after process death. ToolRegistry enablement
and the fixture delivery dictionary also disappear. Losing either the dispatch
reservation or approval consumption can destroy the evidence needed to reject replay.

## Decision

### Storage and scope

Select standard-library SQLite on a local filesystem for the Stage 10 offline proof.
Use explicit versioned migrations, foreign keys, unique constraints, transactions,
and conditional version updates. Opening an adapter must not silently bootstrap or
upgrade canonical tables. A separate migration operation owns schema changes.
Keep in-memory adapters for fast tests. No ORM, broker, scheduler, or network server
is required. Database types remain inside adapters.

The incremental implementation must not advertise a domain-only durable adapter as
a durable Agent Runtime. Until the entire shared transaction boundary is implemented,
the existing in-memory runtime remains explicitly non-recoverable.

### Durability classification

| Category | Records | Reason |
|---|---|---|
| Safety-critical | Workspace, Goal, Task, TaskAttempt, Execution, AgentRun including absolute deadline/working state/budgets; exact definitions, tool versions and enablement; current policies; ActionIntent/request/decisions/reservation/consumption; ToolInvocation/receipt/outcome | Needed to reject stale authority, replay, unsafe retries, and false completion |
| Safety-critical coordination | OrchestrationRun, accepted PlanVersion, materialization, Delegation/attempts/results, active organization pointer | Needed to reconstruct readiness and actor identity without replanning or resetting budgets |
| Historical canonical | Actions, Observations, StateTransitions, Events, graph versions, messages/threads/handoffs, Knowledge source versions/chunks/EvidencePacks, Memory candidates/entries/context packs | Preserve exact provenance and the versions actually available to each run; referenced records also become recovery prerequisites |
| Rebuildable | Lexical indexes, registry query projections, caches, metric/timeline projections | Derived from canonical records; never authorization or outcome truth |
| Ephemeral | Live executor/model objects, locks, transport buffers | Rebind through trusted host composition; never deserialize executable objects |

Persist explicit schema-versioned JSON, not pickle or executable imports. Reject
unknown fields, unsupported schemas, invalid enums, wrong primitive/ID types, and
corrupt relational/payload bindings. Schema evolution requires a migration rather
than coercion or silently filling in new authorization defaults.

### Transactions and claims

All records participating in an application command must use the same durable unit
of work. State, audit, approval reservation, and invocation claim commit atomically.
Conditional writes check the expected Version and require exactly one affected row.
SQLite write serialization supplements, rather than replaces, those version checks.
Independent connections must contend over persisted claims, not Python locks alone.

Consequential I/O is permitted only after the dispatch claim COMMIT returns. No
transaction remains open across executor I/O. A claim is a one-way reservation of
the original actor, exact immutable intent/digest, approval, and invocation identity.
An expired lease is never proof that dispatch did not happen. Do not add leases or
automatic takeover until a tested ownership protocol needs them.

### Crash windows and recovery

| Window | Durable evidence | Safe recovery |
|---|---|---|
| A: before claim commit | No committed invocation claim | Explicit retry can be considered only after current authorization and parent/deadline checks |
| B: claim committed, before executor entry | Reserved invocation, no receipt | Claimed, dispatch unconfirmed; do not infer either success or non-execution |
| C: executor may have written, no receipt | Same local evidence as B | Outcome unknown; connector lookup or manual review, never blind retry |
| D: receipt committed, parent reconciliation incomplete | Exact receipt and invocation | Reconcile local bookkeeping from that receipt without dispatching again |

B and C cannot reliably be distinguished from local state alone. A RecoveryService
must classify incomplete work without calling a model or automatically dispatching.
Unknown is not failure and is not safe-to-retry. A connector's authoritative
`never_received` result may support an explicitly authorized retry; `unknown` may not.
Observed success/failure may produce reconciliation evidence. Preserve original
unknown receipts as history rather than rewriting what the runtime originally knew.

A receipt alone does not satisfy Task or Goal acceptance. Reconcile the pending tool
observation and run bookkeeping, then use existing explicit grounded completion and
orchestration rules. Cancelled/terminal parents never reopen. Original deadlines,
iteration/tool budgets, pinned packs, and approval expiry survive restart unchanged.
Approval remains spent when the result is unknown. Handoffs cannot inherit it.

### Connector contract and limits

A future-facing adapter contract describes idempotency keys, status lookup, remote
cancellation, and compensation separately. The offline fixture should retain its
remote ledger independently of the application database and support never_received,
processed_success, processed_failure, and unknown. Derive a stable key from workspace,
intent, invocation, and exact tool version; a duplicate key with different arguments
must fail. Do not claim distributed exactly-once or universal connector support.
Read-only retries may be less restrictive, but still require current permission,
bounds, and an explicit retry path. Transaction retry must never wrap external I/O.
Database rollback is not external-world rollback; generic compensation is rejected.

### Audit and retention foundation

Audit queries use typed workspace-scoped application boundaries, not caller SQL.
Resolve Goal/Task/Execution/AgentRun/intent lineage, and order timeline events by UTC
timestamp then EventId. Return IDs, digests, versions, and normalized reason codes;
never copy raw document, memory, message, or approval content into generic Events.
Querying a foreign subject must fail rather than reveal whether its content exists.

Retention classes are operational, audit, sensitive, and ephemeral. Operational
records support recovery; audit records preserve structural history; sensitive content
needs separately governed retention; ephemeral state is disposable. Do not select
legal retention periods without requirements. A future tombstone retains identity,
scope, digest, and lineage while marking content unavailable; redacted content cannot
be fabricated on replay or used as active evidence. Deletion/backup propagation,
encryption, legal hold, and compliance certification are not implemented by this ADR.

## Alternatives

- **PostgreSQL:** credible later for server-managed access and concurrent deployment,
  but requires a service and driver without improving the required offline crash proof.
- **In-memory only:** retained for tests, rejected as the recovery foundation.
- **Snapshotting arbitrary Python objects:** rejects explicit schemas, relational
  lineage, safe decoding, and per-record version contracts; not selected.
- **Distributed workflow engine / broker / event sourcing:** no requirement yet;
  would add delivery/replay semantics rather than prove the current ones.

## Consequences and deferred questions

Local-file SQLite is not a multi-region or hostile-tenant security boundary. Trusted
host code and protected database files are assumed. Checks can detect malformed state,
not an administrator rewriting a database into a different internally valid history.
Restoring stale backups must not restore reusable authority; coordinated remote-ledger
reconciliation and a restore runbook remain production prerequisites. Authenticated
recovery operators, file encryption, backups/restore drills, corruption containment,
storage scale, and measured RPO/RTO remain open.

Completion requires genuine reopened-storage tests for all canonical subsystems,
fault injection at claim/I/O/receipt/audit boundaries, competing workers, bounded
workspace audit queries, and all Stage 1–9 regressions. Passing persistence unit tests
alone is not evidence that recovery or Stage 10 is complete.
