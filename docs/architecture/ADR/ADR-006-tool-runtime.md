# ADR-006: Bounded Read-Only Tool Runtime

## Status

Accepted, 2026-09-03. Extends ADR-005 for Stage 3; its Stage 2 decisions remain
historical. AI for judgment. Software for guarantees.

## Context

A model-requested Action does not establish authorization or execution success.
Stage 3 needs exact tool configuration, bounded execution, immutable evidence,
and safe continuation without live services, credentials, or external writes.

## Decision

### Identity, versions, and registry

ToolDefinition is stable workspace-scoped identity, name, description, and risk.
ToolVersion is its immutable sequential published executable contract: executor
kind, named input/output schemas, time/byte limits, no-retry policy, and trust.
ToolRegistry binds an exact ToolGrant (ToolId plus Version) to that snapshot and
a ToolExecutor. No latest-version alias, dynamic import, or model-supplied function
is accepted. Publication cannot replace history or change lineage identity.
Enable/disable is mutable registry policy, separate from immutable versions; its
revision is rechecked after I/O. Publishing v2 does not revoke or replace v1.

AgentDefinitionVersion carries at most three grants, with one exact version per
tool ID. Both `call_tool` action permission and the exact grant are required.
Only `read_only` is executable. `internal_write`, `external_write`, and `high_risk`
are representable but denied, including when explicitly granted. These coarse
Stage 3 categories do not implement the future R0–R4 approval/risk matrix.

### Contracts and scope

Exactly two fixture executors exist: CompanyFactLookup and SourceFactLookup.
The first takes `company_name`; the second takes `source_id` and 1–10 unique `keys`.
The fixed input schema identifiers are `company_lookup.v1` and `source_lookup.v1`.
Both return `facts.v1`: exact keys `schema_version`, `subject`, `facts`, and `notes`.
Subject must match the request; source lookup may return only requested source/keys.
Unknown fields, invalid types/Unicode, duplicate JSON keys, schema mismatches,
reserved receipt source prefixes, and oversized data are rejected.

ToolExecutor is cooperative async: typed validated input and immutable invocation
context in, untrusted JSON text out. No vendor, network, or SDK object crosses the
port. FakeToolExecutor scripts success/failure/timeout, captures calls, and can
block on an async gate. No real external adapter is selected in this stage.

### Invocation, idempotency, and commit boundaries

ToolInvocation is one accepted attempt, bound to Action, AgentRun, TaskAttempt,
Execution, Workspace, and an exact ToolVersion snapshot. Small lifecycle:
`running -> succeeded | failed | cancelled`. Validation/authorization rejects
produce a rejection Event and failure Observation, but no invocation or receipt:
the executor was never called. There is no redundant created/authorized state.

The host-generated ActionId is the invocation key, scoped by workspace/run. A
terminal invocation replay returns current run state without executing or appending
duplicate evidence. A running duplicate fails explicitly without taking ownership.
An intentional new Action with identical arguments is a new budgeted invocation.
The SHA-256 fingerprint covers a canonical tuple of workspace/run/action/tool IDs,
exact version, and normalized input; it is diagnostic, not the idempotency key.
Rejected requests are bounded by iterations, not cached as tool invocations.

Claim the AgentRun version and persist running invocation plus audit before I/O.
Await the executor outside the shared RuntimeStore/DomainStore transaction. On
return, recheck run and all parent versions/states, deadline, registry enablement
revision, and invocation mutation contract. Finish invocation, receipt, Observation,
working state, and audit in one rollback boundary. No tool result completes a Task;
the next model iteration must explicitly propose a grounded `complete_task`.

The existing in-memory runtime store owns these additional records; no standalone
database, event-sourcing architecture, outbox, or distributed exactly-once claim.
A claim commit fault prevents I/O. A result commit fault rolls back partial state;
one best-effort failure reconciliation writes an unknown-outcome receipt, never
re-executing the tool. If storage continues failing, evidence may remain pending
until future durable recovery exists. The run fails rather than claiming success.

### Receipts, Observations, and grounding

ToolReceipt is immutable observed evidence: terminal invocation snapshot, exact
validated input/configuration/timestamps, bounded validated output or normalized
failure, byte metadata, and outcome certainty. Raw malformed/oversized results and
exception messages are not persisted. `serialize_receipt` explicitly exports the
bounded audit representation; it is not an import or automatic replay API.

Successful facts use `tool_receipt:<encoded receipt ID>:<encoded original source ID>`;
components are percent-encoded. Caller facts and tool outputs cannot impersonate
that reserved prefix. Completion matches exact key/value/source against approved
supplied facts or successful receipts from the same workspace/run and granted
ToolVersion. Conflicting/missing required values remain gaps; at least one finding
is still required. No semantic entailment, freshness guarantee, or external truth
claim is introduced. A receipt proves what the runtime observed, not that it is true.

Receipts preserve all accepted facts (at most ten). Observations carry at most five
facts, bounded notes, receipt/version/error references, and `untrusted_tool_data`
trust. Only recent Observations enter the next context. Fixture configuration trust
is `trusted_runtime_fixture`; that does not make output text instructions. Full
receipts remain separately queryable even after an Observation leaves the window.

Tool-enabled runs pin `single-agent-tools-v1`, `read-only-tools-v1`, and
`receipt-facts-v1` protocol/policy/evaluator identities. Existing no-tool agent
versions retain Stage 2 identifiers. Upgrading the Research Brief Agent publishes
a new immutable definition version; no new agent type is introduced.

### Bounds and failure policy

Defaults: 5 tool calls/run, 3/tool, 3 seconds/tool, 2,048 input bytes, 8,192 output
bytes, zero automatic retries. Hard configuration maxima: 20 calls/run or tool,
30 seconds/tool, 4,096 input bytes, 16,384 output bytes. Each call is also bounded
by the remaining run deadline and consumes a model iteration. Existing defaults
remain 5 iterations, 60 seconds/run, last 4 Observations, and 16,000 context text
characters. The default iteration cap means five tool calls leave no iteration
for completion. Source/key/subject fields cap at 128 characters, fact values at
512, notes at 512; context overflow fails instead of silently expanding limits.

RetryPolicy exposes a deterministic no-retry seam and rejects nonzero retry counts.
Accepted invocations consume budgets regardless of outcome; wait/resume retains
counts. Registry/permission/input denials and normalized tool failures normally
return Observations. Codes include validation_error, unauthorized, not_found,
timeout, rate_limited, upstream_unavailable, malformed_output, cancelled,
internal_executor_error, output_too_large, and stale_result. Limits, stale ownership,
storage/runtime faults, and invalid model decisions fail the AgentRun using the
existing reconciliation rules. A Task is not automatically failed by one tool error.

On cancellation or stale completion, append only a terminal invocation/receipt and
audit metadata; discard output and do not change terminal run/parent state. Coroutine
cancellation is propagated after reconciliation. Timeout is a failed invocation
reason, not another lifecycle state. `remote_outcome=unknown` on failure makes no
claim that an upstream process stopped; valid observed output uses `observed`.
Recorded output bytes are accepted bounded payload bytes (zero on failure), not
unbounded transport traffic measurement. Timeouts require cooperative adapters.

## Alternatives

- Arbitrary functions on Agent objects: no enforceable registry/version boundary.
- Tools inside AgentRuntimeService: mixes reasoning coordination and capability I/O;
  use ToolRuntimePort and ToolRuntimeService instead.
- Hash-only deduplication: suppresses intentional repeated reads; Action identity
  distinguishes replay from a deliberate new request.
- Automatic retry, production HTTP, credentials, approval engine, or a queue:
  unnecessary for the two current fixture capabilities; deferred.
- Full receipts in every prompt: unbounded growth; persist evidence separately.

## Consequences

Deterministic tests cover the acceptance, denial, evidence, timeout, cancellation,
stale-result, budget, idempotency, and rollback paths offline. They prove policy
enforcement, not live-model tool-selection quality or immunity to prompt injection.
Python adapters remain trusted in-process code, not sandboxed adversaries. An
adapter can allocate before returning; Stage 3 bounds acceptance/persistence/context,
not hostile process memory. Data and registry state disappear on process exit.

## Deferred Questions

Durable claim/receipt recovery, retention/deletion/redaction, authenticated caller
identity, finer resource scopes, production revocation linearization, full source
snapshots for caller context, artifact storage, live tool conformance, streaming
transport limits, credential isolation, read freshness, semantic evaluation, and
human approval for writes remain unresolved. Stage 4 may explore Company Brain /
Knowledge Retrieval only after the Stage 3 gate; it is not implemented here.
