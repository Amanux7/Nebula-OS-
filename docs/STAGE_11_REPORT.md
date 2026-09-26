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
  restore restrictions.
- Continuation added migration 003 with workspace-scoped `normal`, `maintenance`,
  and `restore_quarantine` modes. A non-normal mode now rejects consequential
  dispatch inside the same canonical transaction that claims ToolInvocation.
- Added a metadata-only inspection catalog over validated canonical categories.
  It omits protected message bodies, source content, Tool payloads and reviewer
  free-text reasons. Its bounded pages are still static offsets/full decode.
- Added authenticated restrictive mode command, SQLite backup API snapshots,
  checksummed manifest, and fresh-destination restores. A restore commits
  quarantine and validates canonical records before publishing its DB filename.
- Added a loopback-only standard-library HTTP host with explicit query routes,
  local sessions, same-origin mutation guard, bounded requests, CSP, safe errors,
  and a separate static inspection console. No agent worker or Tool executor is
  started by the host. The console uses textContent for stored values.
- Added a trusted local CLI for migration, synthetic Aurora Desk seeding,
  credential provisioning, backup, restore, and serving. The seed exercises
  canonical domain, organization, runtime, Knowledge, Memory, approval and
  fixture-write services; it is not a mock landing page.
- Added stale-approved-snapshot drills: a remote effect after backup and a
  revocation after backup both remain blocked by restored quarantine. Recovery
  classifies approved unclaimed intents in quarantine for manual review.
- Backups now reject a multi-workspace source before creating plaintext output,
  recheck the snapshot, and clean up incomplete output on failure.
- Added an offline 200-goal/1000-task fixture and query-plan/timing harness.
  Initial local measurements show full-record decoding dominates several reads;
  no production latency claim is made.

## Current security evidence

The original 35 tests cover credential/session namespace separation; no raw tokens in stored
SQL or reprs; forged/unknown credentials; role and workspace isolation; sensitive
export denial for every role; expiry/logout; account disable and stale version;
audit-failure rollback; migration identity and separation; corrupt role rejection;
Goal pagination/invalid cursors/bounds; guessed foreign Task/account IDs; and
authentication occurring before canonical access.

A separate test closes both databases, returns only primitive credentials/IDs from
the first service graph, reconstructs services, and proves the original session
expiry remains effective. Production token generation is checked separately from
the deterministic test-only generator.

Additional HTTP tests cover real loopback requests, role/workspace isolation,
Host/Origin checks, CSP, safe rendered content and concurrent canonical reads.
Restore tests use independently persisted fixture effects and genuine reopen to
show that an old approval cannot dispatch again after post-backup effects or
revocation. A multi-workspace backup test asserts no plaintext output is left.

## Actual current quality gate

| Check | Result |
|---|---|
| python -m ruff format --check . | 171 files already formatted |
| python -m ruff check . | All checks passed |
| python -m mypy | Success: no issues found in 122 source files |
| python -m pytest -q | **555 passed in 100.45s**, 0 failed |
| git diff --check | Exit 0; LF/CRLF informational warnings only |

All 514 prior regressions remain. Checks used the repository .venv Python. Remote
CI is not claimed for this local Stage 11 checkpoint.

## Not yet implemented — mandatory remaining work

1. Full Stage 11 application-host readiness and lifecycle diagnostics; current
   host performs startup recovery classification but has no production health model.
2. Complete typed inspection DTOs and richer UI lineage for orchestration,
   communication/handoffs, Tool invocations/receipts and restore incidents.
   Current metadata pages are safe but intentionally narrow.
3. Explicit restore release/incident workflow and backup confidentiality/ACL review;
   checksum alone is not authenticity and local files are plaintext.
4. Operational mode incident/release workflow. Current commands can only restrict;
   there is no quarantine release, force retry/success, receipt edit or approval edit.
5. Complete canonical Aurora Desk orchestration/communication seed and an operator
   walkthrough of restore incidents. Empty categories remain honestly empty.
6. Optimize or bound full-record decoding for large inspection queries. The local
   load harness is measurement, not a performance pass.
7. Remaining architecture/documentation updates and full Stage 11 acceptance review.

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

Restore quarantine now has stale approval and independent remote-ledger tests,
but no release workflow or production authentication/backup security. This
checkpoint must not be presented as an operational or production-ready platform.

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
- src/agent_company_os/operator_cli.py
- src/agent_company_os/operator_host.py
- src/agent_company_os/operator_load.py
- src/agent_company_os/operator_ui/index.html
- src/agent_company_os/operator_ui/console.css
- src/agent_company_os/operator_ui/console.js
- tests/test_operator_http.py
- .gitignore
- pyproject.toml

## Recommendation

Continue Stage 11 with complete inspection lineage, restore incident handling and
security/performance acceptance. Recommend Stage 12 only
after the complete Stage 11 evidence gate passes. No new AI autonomy, model provider,
production connector, agent editor, approval write UI or distributed worker was added.
