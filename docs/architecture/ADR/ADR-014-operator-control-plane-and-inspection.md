# ADR-014: Operator Control Plane and Inspection

## Status

Accepted for the local/offline Stage 11 scope, finalized 2026-09-29. The earlier
checkpoint discussion below is retained as decision history; statements about
pending implementation are superseded by the final evidence section. Production
identity, distributed recovery and real connectors remain deferred. See the
[Stage 11 report](../../STAGE_11_REPORT.md) for actual acceptance results.

## Context

The verified starting point is commit ba13fef, with 514 passing tests. Stage 10
preserves canonical state and uncertain outcomes, but its callers are trusted host
code. Exposing those services directly would let callers impersonate operators,
disclose protected payloads, or confuse restored approval with current authority.
Earlier accepted ADRs remain unchanged.

## Decision: operator boundary and authentication

The Operator Control Plane is the human-facing operational boundary for Agent
Company OS. It is not an Agent, Tool, reviewer, manager, or orchestration strategy.
Agents receive no Tool grant or Action for calling it.

Use a locally provisioned OperatorPrincipal bound to exactly one Workspace and
one explicit role. Provisioning is a trusted local bootstrap function, not a
public registration route. It verifies the canonical Workspace before creating an
account. Organizational hierarchy and ReviewerPrincipal records supply no authority.

Select generated 256-bit local credentials exchanged for short-lived opaque
sessions. SecureOperatorSecrets uses secrets.token_hex(32). Only purpose-separated
SHA-256 digests are persisted. This is **not password authentication**: human-chosen
passwords are not accepted and these digests must never be reused as a password
hashing scheme. Production entropy is separate from deterministic test entropy.
Credentials/session values are one-time return values with redacted reprs.

Sessions default to 15 minutes and have a hard one-hour maximum. Injected UTC time
checks both issuance and exclusive expiry. Every use resolves the stored account,
enabled state and version; a caller cannot submit roles or a principal object as
authentication. Account disablement increments its version and invalidates all
existing sessions. Logout revokes one session. Authentication errors do not reveal
whether an account exists. These are local credentials, not SSO, OIDC or MFA.

The identity adapter uses a **separate SQLite database**, bootstrapped explicitly
with checksummed operator_001.sql. Canonical backups must not restore operator
credentials, sessions or enablement. The two stores have no cross-database mutation
transaction: operator commands mutate only identity state; queries do not mutate
canonical state. There is no public API for creating Workspaces here.

### Roles and policy

| Role | Ordinary state | Audit/recovery metadata | Disable local accounts | Sensitive payload export |
|---|---|---|---|---|
| viewer | Yes | No | No | No |
| auditor | Yes | Yes | No | No |
| operator | Yes | Yes | No | No |
| admin | Yes | Yes | Same Workspace only | No |

Operator is reserved for later explicitly governed operational commands; it does
not imply write authority today. No role can approve agent actions, grant Tools,
force success, retry unknown writes, edit receipts or rewrite history.

Provisioning, session issuance/revocation and account disablement append bounded
operator audit records atomically with their identity mutation. The bootstrap
record names the provisioned principal with command local_provision; it does not
pretend that principal authenticated the local filesystem administrator.
Audit tables reject updates/deletes. Failed authentication has no invented actor
and needs bounded host metrics when HTTP is introduced.

## Decision: query seam

OperatorQueryService authenticates and checks backend policy before entering the
canonical transaction. The identity transaction remains open across the bounded
read, so a concurrent disable cannot silently interleave with that read. Lock order
is identity then canonical. Host composition must not reverse this order.

Initial DTOs expose Goal summaries, Task detail, AgentRun identity/state/budget refs,
existing sanitized Goal timelines and recovery classifications. They intentionally
omit instructions, context, message bodies, raw Tool arguments and result content.
Unknown and foreign Task IDs both fail without returning foreign state. The future
HTTP adapter must normalize structured errors rather than return exception details.

Lists use explicit bounded offset cursors (1–100 items, default 25), deterministic
ID order for Goals and existing timeline/recovery ordering. Invalid/noncanonical
cursors fail. Static traversal does not promise snapshot stability across concurrent
insertions. This currently bounds responses, **not database decoding work**: Stage
10 still loads full records. Load measurements and indexed read projections remain
required before Stage 11 can pass.

## Planned remaining decisions and gates

- HTTP candidate: FastAPI with explicit response models and OpenAPI, evaluated
  against a minimal standard-library server. It offers schema/validation tooling
  without placing framework classes in domain code. No HTTP dependency is installed
  in this checkpoint; pin and verify versions when host implementation begins.
- Console direction: separate small same-origin static UI using textContent for
  stored text, not the landing page. No frontend framework is required merely for
  read-only navigation. Session delivery, CSRF/Origin controls, request-size limits,
  rate bounds and security headers must be tested at the HTTP boundary.
- ApplicationHost must deliberately compose canonical services and perform
  schema/integrity checks and recovery classification without starting agents.
- SQLite backup must use the backup API, not a live-file copy. The manifest must
  identify schema, workspace scope and digest. The remote fixture remains separate.
- Restore into a fresh destination must persist restore_quarantine before the
  restored graph can execute. Enforcement must occur in the existing dispatch claim
  transaction, not only the UI. An old approval is not current authority.
- No quarantine-clear path should be supplied until revalidation evidence is
  defined. Operator acknowledgement alone must not revive old consequential intents.
- Health means process liveness; readiness means dependency readability, not absence
  of unknown outcomes. Quarantined inspection should still be possible.
- Seed data must pass real application commands, persist in canonical SQLite and be
  labeled synthetic. Query timing, restore drills and UI tests remain mandatory.

## Alternatives

Plain principal IDs, manager-derived admin roles, blanket approval and UI-only access
control are rejected. Full enterprise identity is deferred. Local generated tokens
avoid adding password enrollment/reset/KDF policy in the first identity slice, but
credential theft remains equivalent to account compromise. A password-based adapter
could later implement the same authentication boundary with a suitable password KDF.

## Consequences and limitations

Identity state is durable and independent of agent behavior. Scoped read DTOs can
support HTTP without exposing raw canonical serialization. The identity DB remains
a trusted local file containing sensitive authentication material. Protect both DB
files with filesystem access controls; hashes are not encryption or tamper proofing.
Restoring an old identity DB is outside canonical restore scope and requires a
separate credential-revocation runbook. Transport security, session theft defenses,
host diagnostics, backup quarantine and the actual console are not yet implemented.

Sources inspected: [Python secrets](https://docs.python.org/3/library/secrets.html)
for OS-backed token generation, and [FastAPI features](https://fastapi.tiangolo.com/features/)
for the HTTP framework evaluation. Local implementation evidence, not those sources,
determines the stage verdict.

## Continuation decision — 2026-09-23

For the loopback-only inspection profile, use Python's standard-library HTTPServer
with a small fixed route adapter, not a general static-file server. FastAPI remains
an alternative for a future network API; this profile needs no async request work,
uploads, external clients or generated API explorer. This avoids new runtime
dependencies, but accepts serialized requests and explicitly is **not a production
HTTP deployment** (Python documents http.server's production limitations).

The host will compose existing authenticated query services. It will not schedule
AgentRuns or bind write executors. Browser sessions use HttpOnly, SameSite=Strict
cookies; Secure is omitted only for this HTTP loopback profile. Mutations require
the exact configured Origin and a custom same-origin request header. Host validation
rejects DNS rebinding. No CORS, raw object routes, sensitive export or approval UI.

Migration 003 adds workspace-scoped operational restrictions and append-only mode
audit. The Tool Runtime checks the restriction in the durable claim transaction.
Backup uses SQLite's backup API. Restore targets a fresh private directory and only
publishes the canonical filename after quarantine is committed and state validates.
Identity and remote fixture databases are excluded. No quarantine release command
is provided: inspecting or acknowledging a case is not sufficient proof to revive
stale authorization. Implementation and drill evidence follows in the stage report.

## Final implemented decision and evidence — 2026-09-29

Retain the separate identity database, generated 256-bit credentials and 15-minute
sessions. No SSO, password scheme, production auth or agent authority is implied.
The HTTP host uses four bounded request workers with one SQLite connection per
request, not an unbounded thread pool. Exact Host/Origin, duplicate-header denial,
custom mutation header, CSP, HttpOnly/SameSite cookie, safe errors and bounded
body/query sizes are tested. Local login is limited to five attempts per 60 seconds
in one process-wide loopback bucket, including successful attempts. No Redis is needed.

Inspection now includes explicit scalar allowlists plus typed links/lineage for
all major canonical subsystems. Goal→Plan/Tasks→Delegation/Attempt→AgentRun→Result
and intent→request/decision→claim/invocation→receipt can be followed. Communication,
Knowledge/Memory and configuration pins are metadata-only. The console renders
stored strings with textContent and has actual Chromium CSP/XSS/navigation evidence.
The Aurora Desk fixture creates a real accepted plan, four delegations (one handoff
replacement), messages, eight runs and results through application services.

Migration 004 adds immutable restore provenance, a local generation counter and
per-intent holds. Restore writes quarantine/provenance/holds before publishing the
fresh database filename. Source and destination paths must be trusted and distinct;
traversal, links/junctions and overwrite attempts fail. Ordinary partial failures
are cleaned; abrupt death can leave unpublished staging output. Files remain
plaintext, checksums unsigned. POSIX mode hints are best-effort; Windows parent
ACL review is required. This does not defeat malicious administrators or path races.

Only an authenticated same-workspace admin can release restore_quarantine. The
canonical transaction validates schema on open, strict canonical decoding, SQLite
integrity/foreign keys, restore provenance, completed recovery classification and
a hold for every existing consequential intent. It then changes only mode and
appends release audit atomically. Role/precondition denials are audited without
changing mode; failed audit persistence rolls back success. An unavailable or
undecodable database cannot persist failure evidence and fails closed instead.

**All intents in the restored snapshot remain held after release.** Unknown cases
can coexist with normal mode because they retain their own dispatch denial and
existing invocation ownership. There is no force/hold-clear API. Old approvals
cannot resurrect authority missing from the original timeline. A committed claim
can be looked up in the independent remote fixture and reconciled without another
dispatch; a pre-claim snapshot may have no such key and must remain unresolved.
Release itself neither looks up remote status nor resumes, consumes, approves,
dispatches, repairs or completes work. Tests prove both later revocation and later
remote effect cannot cause replay after restore/release.

Health is process liveness; readiness validates both databases and service
composition. Recovery cases and quarantine alone do not block inspection readiness.
Safe startup/request metrics have fixed labels; per-workspace startup information
is scoped. Backup command outcomes are bounded local counters, not remote telemetry.

Profiling at 205 Goals/1,009 Tasks shows full decode/validation/encoding dominates:
warm query medians 1.4–1.8 seconds on the measured Windows host. The current full
domain read plan is a table scan; a workspace/kind metadata lookup uses a covering
index, but the latter is not the full current query. No speculative index/projection
is introduced. Host composition instead caps 10,000 canonical/audit records,
32 MiB payload total and 1 MiB per record before decoding; auxiliary row scans
are capped at 20 times the configured record limit. Pages and lineage sections
remain bounded at 100. Tests prove early rejection before codec invocation.
These bounds are not a latency SLO; large-history reads need a later design.

Lock order remains identity→canonical. Separate-connection tests cover Goal writes
and atomic ToolReceipt/Event visibility with bounded local contention. No canonical
transaction holds identity in the opposite order. Full regression: 574 passing
tests, including local real-browser acceptance; see the report for exact commands.

Deferred: production identity/TLS, authenticated connector reconciliation UI,
distributed fencing, reviewed replacement of held work, backup signing/encryption,
identity restore runbook, sustained load, accessible product UX, and production
read projections. Stage 12 is not implemented.
