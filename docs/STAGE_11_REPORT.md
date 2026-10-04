# Stage 11 — Operator Control Plane, Restore Drills and Inspection

Updated: 2026-10-04. **Verdict: PASS for the local/offline Stage 11 scope.**
This replaces the incomplete checkpoint. Stage 12 has not been started.
No production identity, external integration or new autonomous capability is claimed.

## Baseline and checkpoint preservation

Started from clean commit 1863033 (the published operator-host checkpoint), retaining
the Stage 10 durable adapters and existing Stage 11 identity/host/query work.
Read the finish brief, checkpoint report, ADR-014/013 and canonical operator,
backup, recovery, audit, runtime, inspection and console implementations.

Actual baseline before edits:

| Check | Result |
|---|---|
| Ruff format | 171 files already formatted |
| Ruff lint | All checks passed |
| mypy | 122 source files clean |
| pytest | 555 passed in 96.03s |
| git diff --check | Exit 0 |

No blocking pre-existing defect needed repair. The old migration-count assertion
was updated when migration 004 was added; one intermediate full run had 573 passing
tests plus that outdated assertion. The corrected full gate below is the verdict.
Unrelated landing-page work was not changed.

## Implemented outcome and inspection coverage

The loopback console now follows explicit metadata DTOs and structural links for:

- Workspace, OrganizationGraph and versions, Departments, AgentDefinitions and versions.
- Goals, Tasks, TaskAttempts, Executions and AgentRuns.
- OrchestrationRun, PlanVersion, PlanMaterialization, Delegation, DelegationAttempt
  and result references derived from canonical successful runs.
- MessageThread, AgentMessage and HandoffRequest, including participants, versions,
  Task/delegation correlation, reference kinds, status, depth and result lineage.
- Knowledge sources/versions and Memory entries/candidates without protected content.
- ActionIntent, ApprovalRequest, ApprovalDecision, claim/invocation, Tool definitions/
  versions and receipts with risk, executor, status, outcome certainty and safe digests.
- Recovery explanations and related-record links; scoped audit timelines.

OperatorQueryService.lineage returns a typed root and bounded sections over canonical
references. All seeded navigation links resolve in HTTP tests. The Goal walkthrough
includes plan→Tasks→delegations/attempts→runs→results, messages and handoffs. Intent
lineage includes exact request/decisions, claimed invocation and receipt. AgentRun
views retain configuration identity, deadline, iteration/tool/observation counts,
pack references and result availability, not hidden reasoning.

The catalog is an explicit scalar allowlist, not generic object serialization.
Protected model results, message bodies, Knowledge content, Memory text, Tool
arguments/results, instructions, reviewer reasons and secrets stay outside it.
Metadata is bounded; stored text is rendered via textContent. Empty categories
remain empty. Result summaries are projections, not a second canonical result store.

## Restore incident, release and stale authority

Migration 004 adds immutable restore_incidents, restored_intent_holds and
quarantine_release_audit. Restore records backup identity/digest/manifest, time,
principal and local generation. It holds every governed intent in the snapshot,
sets restore_quarantine, validates state, then publishes the fresh DB filename.

Only authenticated same-workspace admin release can move quarantine to normal.
In the shared canonical transaction it validates current decoded records, schema
compatibility, SQLite quick_check/foreign keys, restore provenance, completed
RecoveryService classification and individual holds for every existing intent.
Release and audit commit together. Viewer/role and precondition denials generate
failure evidence; an audit write failure rolls back the mode change. Separate
connections racing release produce one success and one audited denial.

Release does not retry, approve, consume, repair, resume, dispatch, finish Tasks or
call a connector. Unknown recovery cases can coexist with normal mode because
original work remains individually fenced. **Every restored intent stays held after
release**; Stage 11 has no hold-removal API. Ordinary Tool grants, policy, expiry,
actor binding and existing invocation ownership still apply independently.

A stale-approved snapshot taken before a later original-timeline revocation remains
blocked after release. Another drill takes a snapshot after claim but before the
independent remote effect, restores it, then looks up the actual remote outcome:
known success yields one reconciled receipt/consumed approval and zero redispatch;
unknown remains unresolved and cannot falsely complete the Goal. These are genuine
closed/reopened database drills, not surviving in-memory state.

A snapshot predating a claim may lack its remote lookup key. It cannot establish
non-execution or automatically reconstruct the later invocation; its old intent is
held with outcome_unknown. Replacement work requires explicit investigation and
new normal authorization, not a retry loophole. No generalized replacement protocol
is implemented. Release of manually imposed quarantine with no restore provenance
is denied; maintenance release is not supplied.

Audit limitation: authenticated attempts reaching a healthy canonical store are
recorded. Invalid/unknown credentials have no invented principal. A corrupt or
unavailable audit destination cannot promise durable failure evidence: release
fails closed, and safe process diagnostics remain best-effort. No unaudited
successful-release path exists.

## Backup confidentiality and path review

Backups use SQLite's backup API and validate single-workspace scope before creating
plaintext output and again on the snapshot. Manifest size/schema/workspace/digest
are checked; strict canonical decoding and relational validation precede restore.
Names are single path components. Existing destinations and source-as-destination
attempts fail without overwrite. Link/junction paths and linked ancestors are
rejected; roots are trusted configuration, not HTTP input.

Tests cover traversal, overlapping roots, existing canonical destinations, invalid
JSON manifest, wrong digest, unknown migration, corrupt records, partial backup/
restore cleanup and the Windows junction guard. Junction detection is injected
deterministically; no claim is made that a hostile filesystem race was tested.
Ordinary failures remove only exact partial files created by the operation.
Process death can leave a private unpublished staging directory for trusted cleanup.

Snapshot, manifest and roots use best-effort owner-only POSIX modes. On the current
Windows environment chmod is not proof of a private ACL: trusted operators must
verify/configure parent ACLs. No encryption/signature was added. A checksum detects
accidental change under trusted-file assumptions; it does not prove origin against
an attacker who replaces both snapshot and manifest. Identity/session state and the
independent remote ledger are deliberately excluded from canonical backup.

## Aurora Desk and operator walkthrough

The fixture uses real application services and persists Research, Product and
Marketing; Research Agent, Product Analyst and Marketing Writer; five Goals; nine
Tasks; eight AgentRuns; an accepted plan/materialization; four delegations/attempts
including a handoff replacement; canonical results/messages/thread/completed handoff;
Knowledge/Memory; pending and consumed approvals; an invocation/receipt and audits.

OrchestrationService.start_delegation is a narrow extracted claim/start seam used
by the fixture. It does not drive a model itself; execute composes it with the
existing runtime. An optional existing Execution must match workspace/Goal and be
running. Existing one-active-run-per-Execution and budget/version rules remain.

[The walkthrough](engineering/OPERATOR_WALKTHROUGH.md) covers fresh bootstrap,
seeding, local provisioning, serving, authentication, organization/configuration,
Goal→Task→run navigation, communication, approval/receipt/audit/recovery inspection,
backup/restore, quarantine and validated admin release. The host binds no executor
and starts no worker. Synthetic timestamps use the injected system UTC clock;
identities/scenario decisions are repeatable, but expiry is real absolute time.

## HTTP, browser and identity acceptance

The host remains loopback-only (127.0.0.1), with exact Host/Origin validation,
duplicate-sensitive-header rejection, no CORS/transfer encoding, custom mutation
header, bounded JSON bodies/queries, CSP, nosniff, frame denial, no-referrer and
no-store. Sessions use HttpOnly/SameSite=Strict; Secure is omitted only for local
HTTP. Local generated credentials are not password/SSO/production identity.

A single bounded loopback bucket permits five login attempts per 60 seconds,
including success. It is process-local and resets at restart, not distributed
abuse prevention. Four request workers, a small accept queue and local timeouts
bound concurrency. Default access logging is disabled; safe errors omit payloads.

Actual headless Chrome acceptance runs the real HTTP console with a fresh test
profile and local generated credential through a private CDP pipe. Persisted script/
img strings in department descriptions, message correlation metadata, Knowledge
titles and audit safe metadata appear as text: zero injected script/img elements,
dialogs, JavaScript exceptions or CSP violations. Protected model-generated result
content is tested absent from DTOs. Goal lineage links, Task navigation and Recovery
views work under the unchanged CSP. No CSP exception was needed.

Node/Chromium are optional test tools, not package/runtime dependencies. The test
explicitly skips where unavailable; **this Windows gate ran it, with no skips**.
Sandboxed Chrome could not enable its page session, so the acceptance/full runs used
approved execution with fresh workspace temporary directories. A first outside-
sandbox attempt hit sandbox-owned temporary-directory ACLs; isolated paths fixed
the environment issue. Credentials were test-only, passed on stdin, never argv/Git.

Health means process alive. Readiness opens both migrated databases and composes
canonical services; an identity schema fault makes readiness fail while liveness
still responds. Quarantine/unknown cases alone do not make inspection unready.

Startup diagnostics capture duration/open outcome/schema versions and scoped
mode/recovery counts. Fixed-key request counters include auth/authorization failures,
response classes and cumulative request/query durations. BackupService tracks
local command success/failure/duration. Counters are process-derived, not a telemetry
backend or authorization truth; cross-workspace startup state is not exposed.

## Query measurement and explicit bounds

Dataset: Aurora Desk plus **200 added Goals and 1,000 added Tasks**:
205 Goals, 1,009 Tasks, 10 TaskAttempts, 8 Executions and 1,500 domain Events.
Four application-query reads per path: first read then median of three warm reads
in the same local process/file. OS cache was not purged. This is not an HTTP or
production latency SLO; opening per-request services adds validation overhead.

| Application query | First ms | Warm median ms |
|---|---:|---:|
| Goal list | 1575.363 | 1400.506 |
| Goal detail | 1569.809 | 1664.642 |
| AgentRun detail | 1670.847 | 1531.417 |
| Organization departments | 1415.973 | 1690.704 |
| Approval list | 1593.553 | 1483.673 |
| ToolInvocation list | 1473.381 | 1679.382 |
| Recovery scan | 1682.055 | 1551.125 |
| Goal timeline | 1609.329 | 1755.930 |

A profiled Goal detail had one _load (3081 ms cumulative), 3,000 decode_record
calls (1717 ms), recursive codec decoding (2467 ms inclusive), and one _flush
(1662 ms; validation/encoding even on reads). Nested timings overlap and profiler
overhead means they must not be added or compared as uninstrumented latencies.
Catalog projection was 465 ms inclusive. This is not a SQL N+1 lookup explanation:
full record validation plus immutable-container snapshots and encoding dominate.

EXPLAIN for the current raw domain payload read reports SCAN domain_records.
Fetching its 1,233 raw payloads without decoding measured 9.896 ms first / 0.995 ms
warm median (four reads). A possible workspace/kind metadata query uses the existing
covering unique index; that does not eliminate current full canonical validation.

Decision: keep the proven full-read adapter and impose tested pre-decode host bounds:
10,000 canonical/audit records; 32 MiB total payload; 1 MiB per record; auxiliary
lineage/restore/audit tables at most 20 times the configured record limit. Capacity
failure is explicit HTTP 503. Page/lineage section output caps are 100; ordinary
page size is 25. No speculative projection is introduced or used as authorization.
These bounds prevent unbounded decoding, not worst-case latency guarantees.

## Concurrent reads/writes and lock order

Queries hold identity validation before canonical transactions; same-scope release
uses the same ordering. Initial service opening finishes canonical validation before
identity locking. No reverse nested acquisition was added. Separate-connection
tests prove Goal readers wait for commit; ToolReceipt readers and audit queries do
not observe a half-committed receipt/Event pair, and complete within the test's
10-second contention bound. Competing releases have one winner. Existing canonical
claim/version/recovery contention regressions remain intact.

This is a conservative local single-writer profile. Long-running fairness,
multi-host control planes, worker takeover, distributed locks and production load
are not proven by these tests.

## Final quality gate

Repository .venv Python 3.13; offline, no live model/provider or real integration.

| Check | Actual result |
|---|---|
| python -m ruff format --check . | 175 files already formatted (including final documentation) |
| python -m ruff check . | All checks passed |
| python -m mypy | Success: no issues found in 125 source files |
| python -m pytest -q | **574 passed in 60.24s**, 0 failed, 0 skipped |
| git diff --check | Exit 0 |

The recorded full pytest run also used -p no:cacheprovider and a new isolated
--basetemp .local/stage11-final-gate-02 to avoid Windows sandbox/user ACL mismatch.
No prior test was removed or made an expected failure. 555 baseline tests plus 19
new acceptance cases pass. Remote GitHub CI is not claimed by this local report.

## Files added or changed in this finishing pass

### Resumed workspace verification — 2026-10-04

The completed Stage 11 changes survived the usage-limit interruption. The shared
workspace also contains subsequent spatial-console work; that work was preserved.
The original finishing-pass file list below retains its scope. Current combined
verification, including the operator and spatial browser tests, reports:

- Ruff format: 183 files already formatted.
- Ruff lint: All checks passed.
- mypy: Success, no issues found in 127 source files.
- pytest: **581 passed in 133.29s**, zero failures/skips.
- Audio JavaScript contract: 13 checks passed.
- Spatial data JavaScript contract: 15 checks passed.
- git diff --check: exit 0.

The complete pytest run used approved local browser execution with a fresh
isolated `.local/stage11-resume-final-20261004` temporary directory. The earlier
574-test finishing gate above remains dated evidence; seven subsequent tests are
included in this resumed workspace verification. Remote CI is not claimed.

The existing durable inspection fixture was reopened at `http://127.0.0.1:8788/`;
readiness passed. Persisted deadlines were preserved, so old active work may now
classify as expired. No runtime work or new model activity was dispatched.

New:

- docs/engineering/OPERATOR_WALKTHROUGH.md
- src/agent_company_os/adapters/migrations/004_restore_incidents.sql
- src/agent_company_os/operator_scenario.py
- tests/test_operator_acceptance.py
- tests/test_operator_inspection_acceptance.py
- tests/fixtures/operator_browser.mjs

Updated:

- README.md
- docs/STAGE_11_REPORT.md
- docs/architecture/ADR/ADR-014-operator-control-plane-and-inspection.md
- docs/architecture/SYSTEM_ARCHITECTURE.md
- docs/architecture/DOMAIN_MODEL.md
- docs/architecture/DATA_ARCHITECTURE.md
- docs/architecture/AGENT_RUNTIME_ARCHITECTURE.md
- docs/architecture/SECURITY_AND_PERMISSIONS.md
- docs/engineering/DEVELOPMENT_ROADMAP.md
- docs/engineering/TESTING_STRATEGY.md
- docs/engineering/EVALUATION_STRATEGY.md
- docs/engineering/OBSERVABILITY_STRATEGY.md
- docs/project/GLOSSARY.md
- docs/project/OPEN_QUESTIONS.md
- src/agent_company_os/adapters/operational_store.py
- src/agent_company_os/adapters/runtime_store.py
- src/agent_company_os/adapters/sqlite_backup.py
- src/agent_company_os/adapters/sqlite_database.py
- src/agent_company_os/adapters/sqlite_inspection.py
- src/agent_company_os/adapters/sqlite_store.py
- src/agent_company_os/application/backup.py
- src/agent_company_os/application/operations.py
- src/agent_company_os/application/operator_queries.py
- src/agent_company_os/application/orchestration.py
- src/agent_company_os/application/recovery.py
- src/agent_company_os/application/tool_runtime.py
- src/agent_company_os/domain/operations.py
- src/agent_company_os/operator_cli.py
- src/agent_company_os/operator_host.py
- src/agent_company_os/operator_load.py
- src/agent_company_os/operator_ui/console.css
- src/agent_company_os/operator_ui/console.js
- src/agent_company_os/ports/inspection.py
- src/agent_company_os/ports/operations.py
- src/agent_company_os/ports/runtime_store.py
- tests/test_durable_faults.py
- tests/test_durable_foundation.py
- tests/test_operator_http.py
- tests/test_stage11_operations.py

## Completion verdict and remaining limits

**PASS — local deterministic Stage 11.** Complete inspection, authenticated audited
restore release without execution, stale-authority/remote-effect safety, browser
security, readiness, bounded measured reads and regression acceptance are evidenced.

Not implemented: live GPT/Astra/provider calls, production Gmail/Slack/CRM/payments,
MCP, shell/browser tools, approval/agent/organization editing, broader autonomy,
SSO/LDAP/SCIM, a queue, distributed scheduler, worker fleet or Stage 12.

Remaining questions: production identity/TLS and token lifecycle; authenticated
connector operations; worker quiescence/fencing; investigated replacement of held
work; pre-claim backup lookup gaps; signed/encrypted backups and Windows ACL runbooks;
identity disaster recovery; power-loss/soak guarantees; scalable read projections,
snapshot pagination, accessibility/user testing and measured RPO/RTO.

Recommend Stage 12 only as a separately scoped operator usability/performance and
production-hardening design gate before real write integrations. The current local
console and tested restore/lineage boundaries provide evidence for that work.
Stop here; Stage 12 is not implemented.
