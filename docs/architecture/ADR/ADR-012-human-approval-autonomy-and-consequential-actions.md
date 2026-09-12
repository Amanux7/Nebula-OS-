# ADR-012: Human Approval, Autonomy, and Consequential Actions

## Status

Accepted — Stage 9, 2026-09-11. Offline deterministic governance only.
Extends ADR-005/006/009/011 without rewriting their historical decisions.

## Context

Stage 8 supplies exact configuration and organization versions, canonical AgentRuns,
Tool grants, bounded orchestration, handoffs, and atomic in-memory records. A human
decision must authorize an exact proposed operation without becoming a permission
grant, transferring to another actor, or bypassing current safety policy.

## Decision

### Autonomy and risk

AutonomyLevel names Observe (0), Recommend (1), Draft (2), Bounded Execute (3), and
Autonomous Within Policy (4). AgentDefinitionVersion retains its serialized integer
ceiling; validation now permits 0–4 and rejects booleans. Level 0 may inspect authorized
information but cannot complete operational work. Level 1 may respond with a recommendation
and complete an evidence-backed recommendation, never execute a consequential write.
Level 2 requires exact human approval. Level 3 may bypass per-action approval only
when the current policy explicitly permits the exact fixture Tool grant and destination
and enables bounded execution. Level 3 otherwise requires approval. Level 4 is represented
but denied for consequential execution; no general Level 4 runtime exists.

Reuse ToolRisk: read_only, internal_write, external_write, high_risk. Financial,
destructive, and security-sensitive operations remain under the denied high-risk
boundary rather than introducing unused execution categories. Only the exact
send_fixture_message executor kind with external_write risk can enter Stage 9's write
path. Mislabeling that fixture read_only cannot bypass governance. All other write
capabilities remain denied. Risk comes from canonical ToolVersion/ToolDefinition,
never model arguments, role names, or descriptions.

### ActionIntent and payload binding

ActionIntent is immutable proposed consequential work, not an invocation or receipt.
It references the canonical model Action and binds Workspace, AgentRun, Goal, Task,
Execution, exact ToolVersion/operation, normalized arguments, destination, policy
snapshot/version, deterministic risk/effect, creation time, and expiry. TaskAttempt
and exact AgentDefinitionVersion resolve through the immutable AgentRun lineage.
An opaque ActionIntentId derives deterministically from the host-generated ActionId;
there is one intent per Action, not a model-chosen reusable authorization identifier.

SHA-256 covers canonical JSON of workspace, actor/run, Action, exact tool ID/version,
operation, canonical risk, and normalized arguments. Arguments are a strict object
with destination and message, serialized with sorted keys and fixed separators.
JSON formatting/key order is normalized; message whitespace and destination text remain
material. No Unicode-equivalence guessing or free-form prose authorizes execution.
The stored record, canonical Action, validated request, fingerprint, and current
policy must agree. Changing arguments, tool version, destination, or actor requires
a new intent and, where required, new approval.

### ApprovalPolicy, request, and decision

ApprovalPolicy is a workspace-scoped sequential version with exact tool grants,
destination allowlist, explicit reviewer principals, enablement, expiry duration,
and a default-false bounded_execute switch. Its pure evaluator returns deny,
approval_required, or allowed_without_approval. Policy publication is a trusted host
operation, not a model Action. Current policy is stored directly; used policy snapshots
remain on intents for historical interpretation. No policy DSL or external engine exists.

ApprovalRequest binds one intent ID, digest, expiry, and bounded preview. It shares
the intent's identity rather than inventing a second independently reusable request ID.
ApprovalDecision is append-only: approved/rejected, optionally followed by revoked or
expired after approval. Human decisions include an explicit workspace ReviewerPrincipal,
time, exact digest, policy version, and optional bounded reason. Lazy expiry is a
software decision with no impersonated human reviewer. No blanket approval exists.

ReviewerPrincipal is a typed local identity checked against both captured and current
policy allowlists. Unknown and foreign principals fail; manager/lead status is irrelevant.
These are trusted test principals, not proof of authenticated human identity. A future
API must derive principals from authentication rather than accept client-asserted IDs.

### Revalidation and transaction boundary

The existing ToolRuntimeService owns execution. AgentRuntime still accepts only the
existing strict call_tool proposal; there is no model approve/bypass action. Tool Runtime
validates Action binding, exact independent grant, tool resolution, schema, risk,
active parents, deadline, and budgets before dispatch. Governance creates the intent
and request or permits an explicitly bounded Level 3 fixture action.

Immediately before the dispatch claim, it rechecks canonical intent/request/digest,
actor, current expected run version, active Goal/Task/TaskAttempt/Execution, independent
Tool permission, exact enabled ToolVersion, destination, deadline, expiry, revocation,
claim/consumption, current ApprovalPolicy, and applicable organization. Any policy
version change invalidates the old intent, even if the change appears more permissive;
this conservative rule avoids silently interpreting old approval under new policy.

GovernedAction stores current cancellation, immutable request/decisions, a single
invocation reservation, consumption metadata, and optimistic version. RuntimeStore's
existing rollback snapshot includes governance records and active policies. Intent/request
and their events commit together; decisions/events commit together; approval reservation,
running ToolInvocation, run claim, and authorization events commit together before I/O.
Failed claim persistence prevents executor entry. No lock is held over executor I/O.

The successful dispatch claim is the local authorization linearization point.
Cancellation/revocation committed before it wins and prevents dispatch. After it,
cancel-intent/revoke commands reject as already claimed: they cannot promise to cancel
remote effects. Existing run/parent cancellation still invalidates late results.
Registry changes use the existing registry lock/revision protocol; this is not a
distributed transaction or a promise of instantaneous cross-system revocation.

### Waiting, resumption, and handoffs

Approval puts AgentRun and Execution in waiting, keeping the same in-progress Task,
running TaskAttempt, iteration count, deadline, and budgets. A pending tool iteration
marks an approval wait; ordinary context resume cannot clear it. resume_approval resumes
the exact intent and then continues the same runtime loop. Orchestration reports
approval_required and resumes the same Delegation/AgentRun without incrementing its
agent-run count or resetting limits. Rejection, expiry, revocation, and failed
revalidation leave work waiting for explicit host cancellation/recovery, not Goal failure.

Approved intents never transfer through messages or handoffs. A handoff ends the old
actor's attempt; that intent cannot execute. A new actor must create its own intent.
Tool/Knowledge/Memory grants and organization roles never substitute for Tool authority.
Completion is denied while any consequential intent in the run lacks an observed
successful invocation; unrelated supplied facts cannot mask an uncertain delivery.

### Organization interaction

Organization-enabled orchestration pins its graph version onto the child AgentRun.
Before consequential execution, governance requires registry wiring, current active
graph version equal to that pin, and the exact enabled actor eligible at the current
clock instant. Graph activation or membership expiry therefore blocks pending writes.
Historical read/routing pins from ADR-011 are not rewritten. Any graph-version change
is conservatively invalidating for writes, including a structural-only change.
Standalone host-created runs without organization binding still require all explicit
workspace policy and Tool grants. Host composition must preserve orchestration lineage.

### Single use, outcome certainty, and idempotency

Claim reservation prevents approval reuse while I/O is in progress. Terminal receipt
reconciliation marks approval consumed even on failure/unknown outcome; unsuccessful
dispatch does not return reusable authority. A repeated consequential Action or approval
resume fails without another executor call. A deliberate new Action is new work with
new governance, not a replay. The fixture also keys deliveries by ToolInvocation ID.

The protected governance export distinguishes not_executed (no invocation claim),
observed_success, observed_failure (explicit rejection acknowledgment), and outcome_unknown.
Existing receipt values observed/unknown remain compatible; observed_failure extends
them for explicit executor rejection. Timeout, cancellation after dispatch, invalid
output, stale results, and commit ambiguity remain unknown. No receipt claims that
timeout proves no write. A successful receipt is observed evidence, not objective truth.

Result persistence failure uses the existing best-effort unknown-outcome reconciliation
and never automatically retries the executor. Persistent storage failure/process loss
can leave an unresolved claim; everything is in memory. A rolled-back dispatch claim
restores an approval wait where current ownership still matches, without automatic retry.
No crash recovery, durable exactly-once delivery, or distributed approval service is claimed.

### Fixture, bounds, and audit

Exactly one new capability exists: FixtureMessageExecutor/send_fixture_message. It
writes only a local fixture delivery dictionary; it never sends email or calls an API.
Message length is 512 characters, destination length 128, and normal Tool byte/time/call
bounds still apply. Policy allows at most 3 exact tools, 10 destinations, and 10 reviewer
principals; expiry defaults to 30 seconds and caps at 300, also bounded by the original
run deadline. Reviewer IDs cap at 128, reasons at 256, previews at 600, workspace intents
at 200, and decisions at two per request. No production rate limiter is implied.

Audit binds model Action → intent/risk/policy → request/decisions → authorization claim
→ ToolInvocation → ToolReceipt, with parent/configuration lineage through AgentRun.
Events contain IDs, fingerprints, versions, risk, and normalized reasons—not message
text. Explicit protected serialization includes the exact payload for human inspection;
it is not a public log or an authorization import endpoint.

A bounded metadata projection derives intent/request counts, approval/rejection/expiry/
revocation rates, time-to-approval, execution-after-approval, revalidation denial, and
approval-resume replay prevention counts. It is an offline projection, not production
telemetry or a count of every possible malformed host command.

Governance-enabled runtimes pin single-agent-governance-v1 / consequential-actions-v1;
earlier configurations retain their previous identifiers and read-only behavior.

## Alternatives Considered

- Approval as a Tool grant or manager privilege: rejected; one-use consent is separate.
- Reusable approval for an agent/department: rejected; exact structured intent only.
- Execute from an approval service: rejected; existing Tool Runtime remains authoritative.
- Restore approval after timeout: rejected; outcome may be unknown and write may exist.
- Automatically adopt latest graph/policy on resume: rejected; require explicit new work.
- Production connectors, authentication, UI, distributed workers, or a policy DSL:
  deferred; unnecessary to prove the bounded offline authorization contract.

## Consequences and Deferred Questions

Exact approvals and deterministic refusal now compose with the existing runtime, but
this is not production-ready autonomy. Authentication, policy administration, separation
of duties, multi-party approval, secret handling, retention/redaction, durable claims,
crash reconciliation, remote idempotency contracts, compensation, and real connector
conformance remain unresolved. Level 4 and high-risk actions remain denied.

Recommend Stage 10 focus first on reliability, durable claim/reconciliation requirements,
and audit-query foundations before adding real integrations or an approval/graph UI.
Select storage only through requirement-backed evidence. No Stage 10 work is implemented.
