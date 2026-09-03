# Stage 3 — Tool Runtime Report

## Outcome

Stage 3 completion criteria passed locally on 2026-09-03. Implemented a bounded,
typed, read-only Tool Runtime integrated with the existing scripted single-agent
loop. No live model, live external adapter, or external write behavior is claimed.
AI for judgment. Software for guarantees. Stage 4 has not been started.

## Stage 2 Verification

Before Stage 3 changes, the existing checkout passed:

```text
ruff format --check src tests: 39 files already formatted
ruff check src tests: All checks passed!
mypy: Success: no issues found in 39 source files
pytest -q: 87 passed in 1.57s
git diff --check: exit 0, no whitespace errors
```

No blocking Stage 2 defect required correction. Existing Stage 2 tests remain
unchanged and passing. Additive integration preserves the no-tool agent definition
and semantic identifiers; tool-enabled versions have explicit new identifiers.
The reserved receipt source namespace now rejects caller data that impersonates
tool evidence. During Stage 3 verification an invalid-Unicode input edge case was
found and corrected before completion.

## Tool Domain

- ToolDefinition: stable workspace identity, name, description, and risk.
- ToolVersion: immutable exact published contract, executor kind, trust, timeout,
  input/output limits, and no-retry policy.
- ToolInvocation: one accepted Action under an AgentRun/TaskAttempt/Execution,
  with validated input, digest, version/parent claim, timestamps, and lifecycle.
  `running -> succeeded | failed | cancelled`; timeout is a failure reason.
- ToolReceipt: immutable terminal invocation snapshot plus bounded validated output
  or normalized failure and outcome certainty. It is evidence, not model text.

ToolId, ToolInvocationId, and ToolReceiptId are differentiated opaque IDs; production
and deterministic test ID adapters implement generation. ToolObservationData is a
bounded typed payload, not a generic mutable dictionary.

## Tool Registry

ToolRegistry resolves exact ToolId/Version grants only. Publication is sequential,
cannot overwrite a version, and cannot change stable lineage identity. Unknown,
unpublished, disabled, and foreign-workspace versions are rejected. Agent grants
cannot contain ambiguous multiple versions of one tool. Publishing v2 leaves v1
receipts and grants unchanged. Mutable enablement has its own revision, revalidated
after I/O. There is no model-controlled callable, import, or latest alias.

## Tool Executor

ToolExecutor is a provider-neutral cooperative asynchronous port. Validated typed
input and immutable ToolInvocation context enter; untrusted JSON text returns for
strict validation. ToolRegistryPort and ToolRuntimePort separate registry/executor
implementation from AgentRuntimeService. RuntimeStore's existing atomic boundary
owns invocation/receipt persistence; no extra database or queue is required.

FakeToolExecutor scripts results, validation/upstream failures, malformed output,
and timeouts; captures inputs and invocation counts; and supports gate-controlled
blocking/cancellation and race hooks. No vendor SDK or HTTP client is introduced.

## Tool Permissions and Risk Classes

Both the `call_tool` action family and an exact ToolGrant on the immutable
AgentDefinitionVersion are required. Workspace, enabled version, risk, arguments,
active parents, deadline, and budgets are enforced by software. Context and returned
notes cannot widen authority. At most three distinct exact grants are allowed.

ToolRisk implements read_only, internal_write, external_write, and high_risk.
Only read_only can execute; grants do not override that Stage 3 restriction.
Production resource scopes, authenticated callers, and approval policy are deferred.

## Tool Set

Exactly two deterministic read-only fixture tools:

1. CompanyFactLookup: company_name -> bounded approved facts for that company.
2. SourceFactLookup: source_id and unique keys -> bounded matching approved facts.

Input schemas are fixed named contracts company_lookup.v1/source_lookup.v1;
facts.v1 output has schema_version, subject, facts, and notes. Unknown keys and
invalid types, schema versions, subject/source mismatches, duplicate JSON keys,
duplicate facts, invalid Unicode, oversized data, and forged receipt prefixes fail
validation. The optional real external adapter was deliberately not added.

## Agent Runtime Integration

`call_tool -> ToolRuntimeService -> ToolReceipt -> Observation -> next model iteration`.
The model cannot directly execute a function or mutate domain state. Before executor
I/O the runtime commits an invocation claim. After I/O it rechecks versions, state,
deadline, and registry revision and atomically records the result. No lock is held
across the await. Successful tool use alone does not complete Task/TaskAttempt.

The existing Research Brief Agent can be upgraded by publishing a new immutable
definition with exact tool grants. It remains the only supplied agent type.
Tool-enabled runs pin single-agent-tools-v1 / read-only-tools-v1 / receipt-facts-v1;
no-tool runs retain Stage 2 identifiers. Completion still requires an explicit,
validated complete_task decision; Goal satisfaction remains separate.

## Tool Receipts / Provenance

Receipts preserve exact validated request, ToolVersion snapshot, normalized response,
IDs, fingerprint, timestamps, versions, byte metadata, and outcome. Terminal records
are immutable. Explicit serialize_receipt export is JSON-compatible without implicit
object-dictionary output. Raw malformed/oversized data and exception text are omitted.

Each successful finding uses
`tool_receipt:<percent-encoded receipt ID>:<percent-encoded original source ID>`.
The receipt resolves to its invocation, immutable version, and validated input.
A receipt proves what the runtime observed; it does not establish objective truth.
Stored Observations retain the exact bounded preview sent on subsequent iterations.
Receipts survive context-window eviction, but all in-memory records are lost on exit.

## Grounding

Exact key/value/source matching accepts approved supplied facts or successful receipts
from the same workspace/run and granted ToolVersion. Fabricated, altered, failed,
cross-workspace, and foreign-run evidence cannot satisfy this contract. Caller facts
and tool-returned source IDs cannot use the reserved receipt prefix. Conflicting or
missing required values remain gaps; at least one supported finding is required.
No semantic entailment, real-world truth, freshness, or live research quality is proven.

## Runtime Limits

| Limit | Default | Hard configurable maximum |
|---|---|---|
| Calls per run | 5 | 20 |
| Calls per tool | 3 | 20 |
| Tool timeout | 3 seconds, also bounded by remaining run deadline | 30 seconds |
| Input UTF-8 bytes | 2,048 | 4,096 |
| Output UTF-8 bytes | 8,192 | 16,384 |
| Automatic retries | 0 | 0 in Stage 3 |

At most ten facts per receipt, five per Observation, 128 characters per subject/key/
source, 512 per fact value and notes. Existing run defaults remain five iterations,
60 seconds total, four recent Observations, 16,000 context text characters, and
8,000 model-response characters. Each tool request consumes an iteration; five
calls leave no default iteration for completion. Accepted failed calls consume budget;
preflight denials consume iterations but not tool invocations. Counts survive resume.
Oversized output is rejected, never silently truncated into a success receipt.

## Failure Semantics

Validation, unauthorized, not_found, timeout, rate_limited, upstream_unavailable,
malformed_output, cancelled, and internal_executor_error are normalized; size and
stale-result codes provide additional distinctions. Preflight rejection creates
failure Observation/audit without I/O. Tool failures normally permit the next agent
decision, including waiting for context. Runtime/storage faults, stale ownership,
deadline/iteration/tool-budget exhaustion, and invalid model decisions fail the run
through existing parent reconciliation. One tool failure is not automatically Task failure.

Claim failures roll back and prevent I/O. A failed result commit rolls back receipt,
invocation completion, Observation, and working state; one best-effort reconciliation
records failure without re-execution. Persistent storage failure may leave a pending
invocation with a failed run. Tests make that limitation explicit; no success or
automatic recovery is fabricated. Durable reconciliation remains future work.

## Idempotency

Host-generated ActionId, scoped to workspace/run, identifies one invocation. Running
duplicates are explicitly rejected without affecting the owner. Terminal replay does
not invoke the executor or duplicate receipts/events. Deliberately new Actions with
identical arguments are new calls and consume budget. The canonical SHA-256 request
fingerprint is diagnostic, not a distributed exactly-once guarantee. No automatic
retry is enabled; RetryPolicy rejects nonzero retry counts.

## Cancellation

Late output after run or Execution cancellation cannot complete a Task or alter a
terminal AgentRun. Invocation/receipt audit records preserve cancelled/stale outcome
metadata and discard data that cannot safely apply. Coroutine cancellation propagates
after reconciliation. On timeout/failure, remote_outcome is unknown: the system does
not claim an upstream process stopped. Valid observed results use observed. Async
timeouts depend on cooperative trusted adapters; this is not process isolation.

## Injection Boundary

The adversarial fixture returns notes asking to ignore instructions, call
admin_delete_database, and widen permissions. Tests simulate the model following
that request: the registry/policy refuses execution while immutable grants remain
unchanged. Notes are untrusted_tool_data even when the configured fixture origin is
trusted_runtime_fixture. This proves deterministic enforcement, not model immunity.
No secrets or credentials are required or placed in model context.

## Tests

Final local verification after implementation:

```text
python -m ruff format --check src tests
47 files already formatted

python -m ruff check src tests
All checks passed!

python -m mypy
Success: no issues found in 47 source files

python -m pytest -q
155 passed in 2.71s

git -c core.safecrlf=false diff --check
exit 0, no whitespace errors
```

Commands used the existing .venv Python. There are 68 new Stage 3 test cases plus
87 existing cases. Existing CI automatically includes them and remains secret-free
and offline during tests; installing dependencies still downloads packages. No remote
CI execution, live model evaluation, or live tool reliability is claimed.

| Required scenario | Test evidence in tests/test_tools.py |
|---|---|
| A: successful tool use | test_deterministic_tool_eval |
| B/C/K: unauthorized, unknown, foreign tool | test_authorization_before_io |
| D: invalid arguments | test_invalid_arguments_never_execute; input/source edge cases |
| E/F/G: malformed output, timeout, recovery | test_recoverable_failures; test_real_timeout |
| H: budgets | test_tool_budget |
| I: duplicates | test_terminal_invocation_replay; duplicate inflight race; repeated_request fixture |
| J: stale/cancelled | test_inflight_races; test_stale_preflight_and_tampered_replay |
| L: version history | test_history_and_context_bounds |
| M: injection | test_injection_is_data |
| N/O: forged/wrong-scope provenance | test_fabricated_evidence; test_foreign_receipt_and_reserved_source; test_same_workspace_other_run_receipt |
| P: output size | test_recoverable_failures; test_output_contract; test_source_contract_and_utf8_limits |
| Q: rollback | test_atomic_claim_rollback; test_atomic_result_rollback; test_continuing_storage_failure_never_reexecutes |

Additional checks cover bounded preview/context overflow, exact receipt serialization,
audit correlation, retry policy, reserved sources, and no-tool-needed/wrong-selection
fixtures. Scripted correctness is distinct from whether a live model makes good choices.

## Files Changed

Modified:

- README.md
- docs/architecture/AGENT_RUNTIME_ARCHITECTURE.md
- docs/architecture/SECURITY_AND_PERMISSIONS.md
- docs/engineering/DEVELOPMENT_ROADMAP.md
- docs/engineering/EVALUATION_STRATEGY.md
- docs/engineering/OBSERVABILITY_STRATEGY.md
- docs/engineering/TESTING_STRATEGY.md
- docs/project/GLOSSARY.md
- docs/project/OPEN_QUESTIONS.md
- src/agent_company_os/adapters/ids.py
- src/agent_company_os/adapters/runtime_store.py
- src/agent_company_os/application/context.py
- src/agent_company_os/application/research_agent.py
- src/agent_company_os/application/runtime.py
- src/agent_company_os/domain/agent.py
- src/agent_company_os/domain/decisions.py
- src/agent_company_os/domain/events.py
- src/agent_company_os/ports/ids.py
- src/agent_company_os/ports/model.py
- src/agent_company_os/ports/runtime_store.py

Added:

- docs/STAGE_3_REPORT.md
- docs/architecture/ADR/ADR-006-tool-runtime.md
- src/agent_company_os/adapters/tool_executors.py
- src/agent_company_os/adapters/tool_registry.py
- src/agent_company_os/application/tool_runtime.py
- src/agent_company_os/application/tool_serialization.py
- src/agent_company_os/application/tool_validation.py
- src/agent_company_os/domain/tools.py
- src/agent_company_os/ports/tools.py
- tests/fixtures/agent_eval/tool_cases.json
- tests/test_tools.py

No dependency, tooling configuration, or CI workflow changes were necessary.

## Architecture Decisions

[ADR-006](architecture/ADR/ADR-006-tool-runtime.md) records identity/version separation,
grant/risk enforcement, exact registry resolution, minimal invocation lifecycle,
async claims, failure reconciliation, no-retry/idempotency behavior, bounded receipts,
and provenance. ADR-005 was not rewritten; its Stage 2 boundary is explicitly extended.
The glossary replaces the former ambiguous Tool Definition umbrella with precise
ToolDefinition and ToolVersion meanings. No ExecutionStep or AgentInstance returns.

## Deferred Work / Explicitly Not Implemented

External writes (email, Slack, database/filesystem mutation, payments, purchases),
human approval for tools, shell execution, browser automation, unrestricted filesystem
access, MCP, OAuth, external connectors, real network adapters, RAG, embeddings,
Company Brain, knowledge retrieval, long-term Memory, Chief of Staff, delegation,
handoffs, multi-agent communication, Level 3/4 autonomous external actions, graph/org
UI, durable queues, production persistence, and deployment hardening are not added.

## Open Questions and Risks

Pending-claim recovery after crashes; immutable evidence retention versus deletion;
caller-context historical snapshots; source freshness/conflict evaluation; authenticated
principal and finer resource scopes; production revocation races; adapter process/
credential isolation and streaming transport limits remain unresolved. The in-process
adapter may allocate before returning; rejection bounds persistence and context, not
hostile process memory. See OQ-032–036 in [Open Questions](project/OPEN_QUESTIONS.md).

## Completion Gate

All mandatory Stage 3 categories pass: Stage 2 regression verification; tool domain,
registry, executor/fake; call_tool; input/output schema validation; exact read-only
permissions; historical versions; timeout and budgets; idempotency; cancellation and
stale-result handling; immutable receipts; bounded Observations; same-run grounding
and provenance attacks; injection and oversized-output fixtures; recoverable failure;
claim/result rollback; end-to-end tool scenarios; formatter/lint/types/tests; existing
offline secret-free CI configuration; ADR-006 and this report. No external write
capability or live-model quality is falsely claimed.

## Recommended Stage 4

Company Brain / Knowledge Retrieval. The passing Stage 3 gate provides a controlled
capability boundary, bounded evidence snapshots, workspace/run-scoped provenance,
and deterministic grounding tests that can support source-aware retrieval work.
Stage 4 has not been implemented or started automatically.
