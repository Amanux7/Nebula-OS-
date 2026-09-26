# Stage 11 — Operator Control Plane Implementation Checkpoint

Updated: 2026-09-26. **Verdict: INCOMPLETE.** This is an evidence-based checkpoint,
not the Stage 11 completion report. Do not start Stage 12.

## Starting baseline

Commit ba13fef (published Stage 10) had a clean working tree. Read the Stage 10
report, ADR-001–013, system/domain/data/runtime/security architecture, testing,
evaluation, observability and open questions. Inspected canonical stores and the
recovery/audit/Tool boundaries before implementing the first slice.

Actual baseline: Ruff format 150 files already formatted; Ruff lint passed; mypy
103 source files without issues; pytest **514 passed in 28.02s**; diff check exit 0.
No blocking Stage 10 regression or unrelated landing-page change was necessary.

## Implemented outcome

- OperatorPrincipal, differentiated OperatorId, explicit viewer/auditor/operator/admin
  roles, resource policy and safe authentication/access errors.
- Trusted local provisioning generates a 256-bit credential. Authentication exchanges
  it for a purpose-separated short-lived session; client-supplied principal IDs do not
  authenticate. No password, SSO or production identity claim.
- SQLite identity accounts and sessions in a separate explicitly migrated database.
  Tokens are stored only as digests; returned secret wrappers suppress repr output.
- Injected UTC clock and entropy port; default 15-minute sessions, maximum one hour,
  exclusive expiry, canonical account/version revalidation, logout and disablement.
- Account/session mutations and bounded operator audit records commit atomically.
  Audit writes cannot be updated/deleted. Admin disablement is workspace-scoped and
  uses a version predicate. It grants no agent approval or Tool authority.
- Initial OperatorQueryService composes existing canonical services. Authentication
  and role checks precede reads. Goal pages, Task detail, AgentRun summary, sanitized
  Goal timeline and recovery classification have explicit read DTOs.
- Lists use bounded offset pagination with stable static ordering and validated
  cursors. This bounds response size, not Stage 10 full-record decoding cost.
- ADR-014 records identity/query choices and the continuation's loopback host and
  restore restrictions. The host and console remain unimplemented.
- Continuation added migration 003 with workspace-scoped `normal`, `maintenance`,
  and `restore_quarantine` modes. A non-normal mode now rejects consequential
  dispatch inside the same canonical transaction that claims ToolInvocation.
- Added a metadata-only inspection catalog over validated canonical categories.
  It omits protected message bodies, source content, Tool payloads and reviewer
  free-text reasons. Its bounded pages are still static offsets/full decode.
- Added authenticated restrictive mode command, SQLite backup API snapshots,
  checksummed manifest, and fresh-destination restores. A restore commits
  quarantine and validates canonical records before publishing its DB filename.
  This is an initial adapter, not a completed stale-approval/remote-ledger drill.

## Current security evidence

35 new tests cover credential/session namespace separation; no raw tokens in stored
SQL or reprs; forged/unknown credentials; role and workspace isolation; sensitive
export denial for every role; expiry/logout; account disable and stale version;
audit-failure rollback; migration identity and separation; corrupt role rejection;
Goal pagination/invalid cursors/bounds; guessed foreign Task/account IDs; and
authentication occurring before canonical access.

A separate test closes both databases, returns only primitive credentials/IDs from
the first service graph, reconstructs services, and proves the original session
expiry remains effective. Production token generation is checked separately from
the deterministic test-only generator.

## Actual current quality gate

| Check | Result |
|---|---|
| python -m ruff format --check . | 167 files already formatted |
| python -m ruff check . | All checks passed |
| python -m mypy | Success: no issues found in 118 source files |
| python -m pytest -q | **549 passed in 40.47s**, 0 failed |
| git diff --check | Exit 0; LF/CRLF informational warnings only |

All 514 prior regressions remain. Checks used the repository .venv Python. Remote
CI is not claimed for these uncommitted Stage 11 changes.

## Not yet implemented — mandatory remaining work

1. Explicit ApplicationHost, local configuration, shutdown, dependency readiness,
   startup recovery classification, request/auth/query diagnostics.
2. Versioned HTTP API and explicit safe serialization/errors. ADR-014 selects
   a loopback-only standard-library host; it is not wired at this checkpoint.
3. Full application DTO coverage for organization, departments, agents,
   plans/delegations, messages/handoffs, Knowledge/Memory, approvals, Tool
   invocations and receipts. Metadata catalog is only an initial projection.
4. Real separate read-only console, navigation, detail lineage and empty states.
   No UI was built or started; the landing page is untouched.
5. HTTP session delivery, Origin/CSRF controls, rate/request bounds, security headers,
   and stored-HTML/script injection tests.
6. Stale approval and remote-state mismatch restore drills, recovery classification
   of restored claims, and backup confidentiality/ACL review.
7. Operational mode incident/release workflow. Current commands can only restrict;
   there is no quarantine release, force retry/success, receipt edit or approval edit.
8. Canonical Aurora Desk seed command, inspection/recovery/restore demos.
9. Measured query/load fixture, query-plan evidence, concurrent read/write tests and
   any justified indexed projections. No performance measurements are claimed yet.
10. Remaining architecture/documentation updates and full Stage 11 acceptance review.

## Limits and open questions

Local bearer credentials are not enterprise identity. Filesystem administrators
remain trusted; encryption, MFA, password enrollment/reset, credential rotation,
rate limiting and production session controls remain unresolved. Identity database
restoration requires a separate security runbook and is not part of canonical backup.
Generated tokens must never be replaced with human passwords while retaining plain
SHA-256 hashing. No raw credential should be logged or committed.

Pure OperatorPolicy is not an authentication boundary by itself. Future routes must
use OperatorService/OperatorQueryService, not accept a serialized principal. The
low-level stores remain trusted adapters, not APIs. Queries hold identity then
canonical transaction locks; this conservative local ordering needs measured behavior
before scaling. Pagination is static offset semantics, not a cross-request snapshot.

Most importantly, restore quarantine's durable dispatch gate and fresh restore
adapter have only initial integration coverage. The required stale-approved-payload
and independent remote-ledger drills have not run. This checkpoint must not be
presented as an operational or production-ready platform.

## Files added or changed

- README.md
- docs/STAGE_11_REPORT.md
- docs/architecture/ADR/ADR-014-operator-control-plane-and-inspection.md
- docs/architecture/SECURITY_AND_PERMISSIONS.md
- docs/engineering/DEVELOPMENT_ROADMAP.md
- src/agent_company_os/domain/operator.py
- src/agent_company_os/ports/operator.py
- src/agent_company_os/ports/store.py
- src/agent_company_os/adapters/operator_store.py
- src/agent_company_os/adapters/migrations/operator_001.sql
- src/agent_company_os/adapters/in_memory.py
- src/agent_company_os/application/operator.py
- src/agent_company_os/application/operator_queries.py
- tests/test_operator.py
- src/agent_company_os/domain/operations.py
- src/agent_company_os/ports/operations.py
- src/agent_company_os/ports/inspection.py
- src/agent_company_os/ports/runtime_store.py
- src/agent_company_os/adapters/migrations/003_operations.sql
- src/agent_company_os/adapters/runtime_store.py
- src/agent_company_os/adapters/sqlite_database.py
- src/agent_company_os/adapters/sqlite_store.py
- src/agent_company_os/adapters/operational_store.py
- src/agent_company_os/adapters/sqlite_backup.py
- src/agent_company_os/adapters/sqlite_inspection.py
- src/agent_company_os/application/backup.py
- src/agent_company_os/application/operations.py
- src/agent_company_os/application/tool_runtime.py
- tests/test_durable_faults.py
- tests/test_durable_foundation.py
- tests/test_stage11_operations.py

## Recommendation

Continue Stage 11 with the HTTP composition and restore-quarantine enforcement,
then build the console against those real query services. Recommend Stage 12 only
after the complete Stage 11 evidence gate passes. No new AI autonomy, model provider,
production connector, agent editor, approval write UI or distributed worker was added.
