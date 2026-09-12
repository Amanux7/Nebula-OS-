# Stage 9 — Human Approval, Autonomy Levels, and Consequential Action Governance

Verification date: 2026-09-11. Scope: deterministic, offline, trusted-host runtime.

## Outcome

PASS for the requested Stage 9 fixture-governance scope. An exact consequential
proposal can be evaluated, approved by an explicit local reviewer, revalidated,
reserved once, executed through the existing Tool Runtime, and audited through its
receipt. Rejection performs no write. No production integration or Stage 10 feature
was implemented. This is not production authentication or distributed exactly-once delivery.

## Stage 8 baseline

Reviewed the Stage 8 report, ADR-001 through ADR-011, requested architecture/engineering
documents, and the implementations of configuration, AgentRun, Tool Runtime,
orchestration, organization, communication/handoffs, events, and shared transactions.

The complete baseline actually ran before changes:

| Check | Result |
|---|---|
| `python -m ruff format --check .` | 126 files already formatted |
| `python -m ruff check .` | All checks passed |
| `python -m mypy` | Success: no issues found in 83 source files |
| `python -m pytest -q` | 386 passed in 6.55s |
| `git diff --check` | Passed, exit 0 |

Existing uncommitted Stage 7/8 work and the unrelated untracked landing-page directory
were present at baseline and preserved. The broad root formatter count includes
files outside the backend's `src`/`tests` CI scope; it is not a count of files added
by Stage 9. No landing-page implementation was edited for this task.

## Stage 8 corrections

No blocking pre-existing failure required correction. Stage 9 explicitly extends the
Stage 3 read-only boundary and Stage 8 historical graph policy for consequential fixture
execution. Earlier ADRs remain unchanged. New governance-enabled runtime identifiers
prevent the new semantics from being silently labeled read-only-tools-v1.

## Autonomy model

AutonomyLevel defines 0 Observe, 1 Recommend, 2 Draft, 3 Bounded Execute, and 4 Autonomous
Within Policy. AgentDefinitionVersion retains the compatible integer ceiling with strict
0–4 validation. Level 0 cannot execute consequential actions; Level 1 can recommend
without operational authority. Level 2 requires approval of an exact intent. Level 3
executes without per-action review only under an explicitly enabled policy for the exact
fixture Tool grant and destination; otherwise it requires review. Level 4 consequential
execution remains denied. Organizational position never raises autonomy.

## ActionIntent

An immutable ActionIntent binds workspace, original AgentRun and canonical Action,
Goal/Task/Execution lineage, exact ToolVersion and operation, normalized arguments,
destination, canonical risk, policy snapshot/version, deterministic policy effect,
fingerprint, creation time, and expiry. TaskAttempt and AgentDefinitionVersion are
reachable through the immutable AgentRun rather than duplicated as mutable configuration.
Its typed ID is derived from the host-generated ActionId; a model cannot select a
previous approval identity. GovernedAction holds versioned lifecycle metadata separately
from the immutable proposal.

## Risk classification

The existing ToolRisk taxonomy remains canonical: read_only, internal_write,
external_write, and high_risk. Financial, destructive, and security-sensitive capabilities
remain denied rather than adding unused risk-specific executors. Only
send_fixture_message with canonical external_write risk is eligible for Stage 9's
write path. Mislabeling that fixture read_only, or supplying model approval/risk flags,
does not bypass governance. Other non-read-only executors remain denied.

## ApprovalPolicy

The pure evaluator returns deny, approval_required, or allowed_without_approval from
the agent ceiling, exact Tool grant/version/kind/risk, destination, and current scoped
policy. The application/Tool Runtime adds current runtime, independent Tool permission,
expiry, single-use, and organization checks. Policy changes publish sequential versions;
any changed current policy invalidates a captured intent, even if apparently looser.
Each used policy remains historically available in its immutable intent snapshot.

## ApprovalRequest / Decision

ApprovalRequest identifies exactly one intent and fingerprint, expiry, and bounded
human-readable preview. It shares the intent's identity instead of creating a reusable
approval token. ApprovalDecision is append-only approved/rejected, with approved followed
only by revoked or expired. Human decisions include explicit ReviewerPrincipal,
workspace, time, digest, policy version, and bounded reason. Software expiry is explicitly
not attributed to a human. Reviewers must appear in captured and current policy allowlists;
unknown/foreign reviewers and manager-role spoofing fail. Authentication is deferred:
an API must eventually derive principals from an authenticated session, not caller text.

## Payload binding

SHA-256 binds canonical workspace, run, Action, Tool ID/version, operation, risk, and
normalized destination/message arguments. JSON key order and formatting normalize;
message whitespace and destination text remain material. Changing payload, destination,
actor, or tool version cannot reuse approval. The protected explicit export contains
exact arguments and digest for review, plus structured lineage and decision history.
Preview text is informational, never the authorization object.

## Expiry / revocation / kill controls

Approval expiry defaults to 30 seconds, caps at 300, and is never later than the original
run deadline. The injected clock evaluates expiry lazily and records an expiry decision
when the resume path detects it. Rejected, revoked, expired, and cancelled intents cannot
execute. cancel-intent is a trusted-host kill operation; revocation requires an authorized
reviewer. After a dispatch claim wins, intent cancellation/revocation rejects as already
claimed and makes no promise to reverse an external effect. Existing run cancellation
still rejects late results. Rejection leaves logical work waiting, not a failed Goal.

## Revalidation

Immediately before dispatch the runtime checks canonical Action/intent/request equality,
exact payload fingerprint and destination, actor, expected run version, active parents,
deadline, independent exact Tool grant, enabled ToolVersion, current policy, valid/unspent
approval, and organization eligibility. Missing adapter wiring fails closed. Handoff or
other actor changes require a new intent. Changed policy is never waived by a prior
human decision. No blanket approve-agent or approve-department operation exists.

## Tool Runtime integration

The existing call_tool proposal/parser, ToolRegistry, exact grants, input/output validators,
ToolRuntimeService, ToolInvocation, and ToolReceipt remain the execution path. A single
FixtureMessageExecutor writes only its local delivery dictionary. It does not connect
to Gmail, Slack, CRM, a database, shell, browser, or network.

Intent/request persistence is atomic with audit and waiting transitions. Approval
reservation, ToolInvocation creation, AgentRun claim, and authorization audit share
RuntimeStore's existing rollback boundary before executor I/O. A failed claim cannot
dispatch and restores an approval wait when ownership still matches. Result reconciliation
persists receipt/consumption/observation atomically; a result commit fault never causes
automatic re-execution. Repeated consequential Action dispatch fails explicitly.

## Orchestration integration

AgentRun and Execution wait on approval while Task remains in progress and TaskAttempt
remains running. Orchestration reports approval_required. Exact-intent resume preserves
the same Delegation, AgentRun, TaskAttempt, Execution, original deadline, model iteration,
and Tool-call counters. It continues through the existing runtime and result reconciler;
it does not create a new actor or reset budgets. Ordinary context resume cannot clear
approval. Revalidation failure leaves orchestration waiting. A consequential run cannot
complete while one of its intents lacks an observed successful invocation.

## Organization interaction

Organization-enabled child runs pin the orchestration graph version. Consequential
governance requires the same current active graph version and current effective
eligibility of the exact agent. New graph activation or expired membership blocks old
pending writes. This deliberately stricter write rule does not rewrite Stage 8 historical
read/routing pins. Managers/leads are not automatically reviewers or Tool grantees;
Knowledge and Memory grants remain separate. Standalone trusted-host runs without an
organization binding still require workspace policy and independent Tool grants.

## Idempotency

One host Action produces one intent. One intent reserves at most one ToolInvocation;
pending dispatch cannot reuse approval. Terminal reconciliation consumes approval even
if the result is failed or unknown, so uncertainty never returns reusable authority.
The fixture also keys deliveries by invocation ID. A deliberate new Action is new work
and must pass governance again; it is not content-based global deduplication.

The authorization linearization point is the committed local dispatch claim. Revoke/cancel
before that claim wins; after it, remote cancellation cannot be promised. In-memory state
loss destroys this guarantee across process restarts. There is no durable recovery,
distributed exactly-once claim, or live connector contract.

## Outcome certainty

Protected exports distinguish not_executed, observed_success, observed_failure (an explicit
executor rejection acknowledgment), and outcome_unknown. Stage 3 observed/unknown receipt
values remain supported, extended by observed_failure. Timeout, cancellation after write,
invalid/stale output, and commit ambiguity remain unknown. Tests prove an actual local
fixture delivery can exist even when cancellation makes its accepted result unknown.
Unknown delivery cannot be concealed by completing a Task from unrelated supplied facts.

## Security

The 58 new tests cover autonomy 0–3 and denied 4, canonical high-risk rejection, exact
payload/destination/tool/actor/workspace binding, explicit reviewer identity, stale runs,
cancelled Tasks/Executions, missing Tool permission, changed policy/organization,
expiry/revocation/rejection, replay/duplicate dispatch, prompt JSON bypass attempts,
handoff source termination, atomic request/decision/claim persistence, result-commit
ambiguity, cancellation-after-write, bounds, normalization, previews, and audit redaction.
All 386 previous tests remain passing, including Knowledge/Memory/organization authority
isolation. These are deterministic contract tests, not perfect injection resistance,
production authentication, or human-review quality evidence.

## Limits

| Bound | Implemented limit |
|---|---|
| Fixture message | 512 characters |
| Destination | 128 characters; exact policy allowlist |
| Policy tool grants | 3 |
| Policy destinations | 10 |
| Policy reviewers | 10; typed workspace principals |
| Reviewer ID | 128 characters |
| Approval lifetime | 30 seconds default; 300 maximum; original run deadline also applies |
| Review reason / preview | 256 / 600 characters |
| Workspace intents | 200 |
| Decisions per request | 2, only legal append-only sequences |
| Model/Tool budgets | Existing per-run iteration, deadline, call, byte, and timeout bounds |

Audit Events contain IDs, digests, canonical risk/policy versions, and normalized reasons,
not raw fixture messages. governance_metrics projects request and decision counts/rates,
time-to-approval, dispatch-after-approval rate, revalidation denial, and approval-resume
replay prevention. This is a scoped offline projection, not a production monitoring service
or an exhaustive metric for every malformed host API call. Production rate limits and
retention/redaction remain open.

## Deterministic approval demo

The executable departmental scenario creates Research, Product, and Marketing departments
with exact registered agents. Research produces a grounded pricing result; Product consumes
its canonical TaskResultReference; Marketing consumes Product's result and proposes one
send_fixture_message to customer:paper-kite. Its Level 2 run waits, an explicit reviewer
approves the digest, the runtime revalidates, the fixture writes once, the receipt persists,
the same actor finishes, and orchestration satisfies the Goal.

Parallel scenario variants reject the request or activate a new organization version
after approval. Neither writes; the Goal remains active and orchestration safely waiting.
No model provider, real customer system, authentication service, or network is involved.

## Test results

Final full code gate actually executed on 2026-09-11 using the repository virtual environment:

| Command | Result |
|---|---|
| `python -m ruff format src tests` | 3 files reformatted; 87 unchanged |
| `python -m ruff format --check .` | 132 files already formatted |
| `python -m ruff check .` | All checks passed |
| `python -m mypy` | Success: no issues found in 88 source files |
| `python -m pytest -q` | 444 passed in 8.37s; zero failures |
| `git diff --check` | Passed, exit 0 |

The Stage 9 subset adds 58 tests. Existing CI already runs backend formatting/lint,
mypy, and tests without secrets or live services; no CI dependency or workflow change
was required. These are local results, not an assertion that GitHub CI or review ran.

## Files changed

Added for Stage 9:

- `src/agent_company_os/domain/governance.py`
- `src/agent_company_os/application/governance.py`
- `src/agent_company_os/application/governance_serialization.py`
- `src/agent_company_os/adapters/fixture_message.py`
- `tests/test_governance.py`
- `docs/architecture/ADR/ADR-012-human-approval-autonomy-and-consequential-actions.md`
- `docs/STAGE_9_REPORT.md`

Implementation files extended:

- `src/agent_company_os/adapters/runtime_store.py`
- `src/agent_company_os/application/context.py`
- `src/agent_company_os/application/orchestration.py`
- `src/agent_company_os/application/runtime.py`
- `src/agent_company_os/application/runtime_serialization.py`
- `src/agent_company_os/application/tool_runtime.py`
- `src/agent_company_os/application/tool_validation.py`
- `src/agent_company_os/domain/agent.py`
- `src/agent_company_os/domain/decisions.py`
- `src/agent_company_os/domain/events.py`
- `src/agent_company_os/domain/orchestration.py`
- `src/agent_company_os/domain/tools.py`
- `src/agent_company_os/ports/runtime_store.py`
- `src/agent_company_os/ports/tools.py`

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

This list identifies Stage 9 changes, not every difference from HEAD. Pre-existing
Stage 7/8 changes remain local, along with the unrelated landing-page directory.
No commit, push, pull request, or GitHub review was performed for this stage.

## ADR-012

[ADR-012](architecture/ADR/ADR-012-human-approval-autonomy-and-consequential-actions.md)
records autonomy, risk reuse, exact intents/fingerprints, reviewers, expiry/single use,
current-policy checks, actor binding, permission independence, waiting/resume,
organization invalidation, kill/claim ordering, receipt certainty, local idempotency,
fixture limits, and deferred production work. Prior accepted ADR history was preserved.

## Deferred work

Not implemented: real Gmail/Slack/Teams/CRM writes, payments/transfers, production
database mutations, shell/browser writes, GitHub/cloud writes, MCP writes, unrestricted
Level 4, blanket approvals, production authentication, approval UI, distributed approvals,
new queues/databases, or real integrations. No Stage 10 implementation was started.

## Open questions

- How will reviewer and policy-administrator identities be authenticated and separated?
- Which actions need multiple reviewers and calibrated human comprehension tests?
- How should durable claims and uncertain outcomes recover after process/storage loss?
- What remote idempotency, compensation, and cancellation contracts will each connector support?
- How should sensitive approval payloads be retained, redacted, deleted, and access-controlled?
- Which policy changes may eventually be safely compatible with existing intents?
- What distributed revocation, rate limits, and audit guarantees are required before production?

## Completion verdict

PASS for Stage 9's bounded deterministic scope: explicit consequential intents,
canonical risk, autonomy enforcement, exact single-use approval, independent Tool
permission, expiry/revocation, current-state/policy/scope revalidation, safe wait/resume,
local duplicate prevention, full stored audit lineage, observed/unknown outcomes,
offline write/rejection demos, and the full quality gate are present. ADR-012 and this
report are included. Production-readiness claims remain explicitly excluded.

## Recommended Stage 10

Recommend **Reliability, Recovery, and Audit-Query Foundations** before production
connectors or an approval/graph UI. Stage 9 makes authorization deterministic but leaves
claims and receipts in memory. Next evidence should define durable transaction and
reconciliation requirements, test process loss around dispatch, preserve uncertain
outcomes without unsafe retries, and establish workspace-scoped audit queries with
retention/redaction requirements. Choose storage only through an evidence-based ADR.
Stage 10 is recommended, not implemented.
