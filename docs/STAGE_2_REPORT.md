# Stage 2 — Single-Agent Runtime Report

## Outcome

Implemented and locally verified on 2026-09-03. The Stage 2 deterministic runtime
completion gate passes. One Research Brief Agent operates inside the existing
domain lifecycle with a provider-neutral model port, scripted adapter, validated
internal decisions, versioned runtime identity, bounded context, and audit records.

**No live LLM was integrated or called.** The fake adapter supplies predetermined
decisions. These results prove runtime behavior against untrusted proposals, not
the research quality or reasoning ability of a live AI model. The optional live
adapter is deliberately deferred; it is not a completion dependency in this brief.

## Stage 1 verification and corrections

Stage 1 code existed uncommitted, but no report or completed verification existed.
Development dependencies first had to be installed into `.venv`.

Before corrections: pytest **45 passed, 1 failed**; mypy passed for 27 source files;
Ruff found 11 lint errors and 13 unformatted files. The failed demo expected the
wrong number of Events/transitions; the actual lifecycle requires 21 and 14.

Corrections before adding runtime code:

- Fixed that assertion, formatting/lint findings, and untyped test helpers.
- Added persistence validation for audit subject/workspace/version consistency,
  legal transitions, and immutable historical fields.
- Moved defensive attempt lineage/uniqueness/bound checks inside the store lock.
- Added a rollback transaction boundary and five store regression tests.
- Created [the missing Stage 1 report](STAGE_1_REPORT.md) from actual results.

Verified cleanup gate: **51 tests passed**, Ruff format/lint passed, strict mypy
passed for 28 source files. No claim is made that these passed at an earlier date.

## Agent runtime

AgentRuntimeService is separate from DomainService. It loads approved parents,
claims a versioned invocation, assembles a bounded request, calls ModelPort outside
the transaction lock, parses untrusted JSON, checks policy and grounding, revalidates
parent/run versions and states, then commits an internal action result.

Completion atomically succeeds the TaskAttempt, completes its Task, succeeds the
Execution when all Goal tasks are completed, updates AgentRun, and appends audit
records. It does **not** automatically satisfy the Goal. A fault injected after the
run save proves partial completion rolls back before categorized failure is recorded.

## AgentDefinition and AgentRun

AgentDefinition is stable workspace-scoped identity/name. AgentDefinitionVersion
is a sequential immutable published snapshot of role, instructions, action grants,
autonomy ceiling, model identity, and schema version. There is no mutable latest
alias in a run. Publication of an existing version is rejected.

AgentRun is a standalone immutable/versioned record bound to one TaskAttempt,
Execution, Task, Goal, exact definition snapshot, limits, and scoped supplied
context. It records policy/runtime/evaluator version identifiers. Lifecycle:
running → waiting → running, then succeeded, failed, or cancelled as permitted.
Terminal identity/history cannot reopen. One run per attempt and one active run
per Execution are enforced. Concurrent duplicate invocation is rejected by a
persisted pending-invocation guard; there are no distributed locks.

## Model port and adapters

ModelPort accepts a typed AgentModelRequest and asynchronously returns untrusted
JSON. The request separates configuration/instructions, Goal/Task information,
constraints, allowed actions, iteration bounds, supplied data, and recent
Observations. No provider SDK types enter the domain or runtime core.

- **Implemented:** FakeModel (`scripted-v1`), with predetermined results, errors,
  captured requests, and deterministic test hooks.
- **Deferred:** live adapter, credentials, provider selection, token usage, paid
  evaluations. No provider success is claimed. ADR-005 is therefore the runtime
  decision, not an initial-provider decision.

Async adapters must be cooperative and nonblocking. Coroutine timeout enforcement
is not a sandbox for hostile adapter code or a guarantee that remote work was stopped.

## Decision contract

Schema version 1 has exactly `schema_version`, `action_type`, and `payload`:

```json
{
  "schema_version": 1,
  "action_type": "complete_task",
  "payload": {
    "findings": [
      {"key": "A.price", "value": "100/month", "source_id": "source_1"}
    ],
    "gaps": ["B.price"]
  }
}
```

The parser rejects unknown/extra fields, duplicate JSON keys, unsupported versions,
unknown actions, malformed/empty/oversized output, and invalid typed payloads.
There is no requested hidden chain-of-thought field. Intermediate response messages
are capped untrusted drafts, not completion evidence.

## Actions, Observations, and Working State

The exact action set is `respond`, `request_more_context`, `complete_task`.
They cannot browse, call APIs, write files, send messages, or execute external tools.

Action records the typed request. Observation records a result or approved context
input with provenance/trust and optional Action correlation. Implemented outcomes
include action_accepted, completion_result, validation_error, and context_received;
the action_rejected kind is reserved in the small enum, not an additional executor.

AgentWorkingState holds iteration, recent Observations, missing fields, and pending
invocation state. It is bounded current-run state, **not Memory**. Canonical audit
records are separate; current context can be replaced by approved resume input.
Full historical source-snapshot retention across replacements remains deferred.

## Policies and runtime limits

ActionPolicy (`internal-actions-v1`) enforces the published action allowlist and
requires at least Level 1 for internal task completion. No policy supports Level 3/4
external behavior. Source text cannot change grants.

Default limits:

| Bound | Default |
|---|---:|
| Decision iterations, including resumed work | 5 |
| Total run deadline | 60 seconds |
| Model invocation timeout | 5 seconds |
| Recent Observations in context | 4 |
| Assembled context text budget | 16,000 characters |
| Raw decision response | 8,000 characters |

Configuration also has hard positive-integer maxima. Source collections and fields
are bounded. Character budgets are not token accounting. The total deadline and
iteration count never reset on resume. Expired waiting work is failed when resume
is attempted; no background expiry scheduler is implemented.

Cancellation invalidates late results. An in-flight cooperative model invocation
may return at its remaining timeout unless its coroutine is cancelled by the caller.
The suite covers both a simulated timeout and an actually pending async invocation.

## First agent and grounding

Research Brief Agent uses only task-scoped supplied facts. Completion requires one
or more findings with exact key/value/source matches. Every unambiguous required
key must be represented; missing/conflicting keys must be gaps. A fabricated value
cannot become supported merely by reusing an existing source ID. Software generates
the summary and source list from accepted findings.

This deliberately extractive contract does not verify source truth, interpret all
natural-language acceptance criteria, or establish general paraphrase entailment.
It is a narrow production-oriented boundary, not a universal hallucination detector.

## Deterministic demo and wait/resume

The integration suite creates a Workspace, activates a Goal, creates/starts a Task,
starts an Execution and TaskAttempt, publishes the one agent definition, starts an
AgentRun, and accepts a grounded structured completion through the real runtime.
It asserts TaskAttempt/Task/Execution results and correlated audit records.

Missing-context flow puts AgentRun and Execution in waiting while TaskAttempt stays
running and Task stays in_progress. Tests supply additional approved facts and resume
the same identities with the remaining iteration/deadline budget. No chat UI or
external retrieval is added.

## Failure scenarios tested

- Malformed/empty/oversized output and unknown schema/fields/actions.
- Unauthorized operations, restricted definition policy, and invented facts.
- Conflicting evidence, irrelevant facts, and unsupported completion.
- Provider outage/error normalization, rate limit, fake timeout, real async timeout.
- Total deadline before accepting output and waiting expiry on resume.
- Iteration exhaustion and no budget reset through resume.
- Stale parent state/run version, duplicate start/drive, and cancellation race.
- Cross-workspace definition/run references and immutable historical configuration.
- Context overflow before model invocation.
- Atomic rollback of run, attempt, task, execution, and audit on injected failure.
- Explicit JSON-safe public run result serialization.

Provider/model failure fails an attempt and Execution, not the business Task as
impossible. An in-progress Task returns to ready; the Goal remains active. Cancellation
is distinct. No automatic retry or silent terminal-parent rewrite occurs.

## Security / injection fixture and evaluation dataset

`tests/fixtures/agent_eval/cases.json` contains six versioned cases:
complete_context, missing_fact, conflicting_fact, irrelevant_context,
instruction_attack, unsupported_completion. The adversarial source asks for
instruction override, false pricing, and `delete_database` authority.

Scripted valid/invalid decisions prove that context does not widen runtime policy
and that missing/conflicting facts cannot be fabricated into accepted output.
They do **not** prove a live model always resists injection. Caller approval of
supplied data is an application responsibility; an authenticated API is not built.

## Test results

Actual final local verification using `.venv/Scripts/python.exe`:

```text
python -m ruff format --check src tests: 39 files already formatted
python -m ruff check src tests: All checks passed!
python -m mypy: Success: no issues found in 39 source files
python -m pytest -q: 87 passed in 1.61s
git diff --check: no whitespace errors
```

Tool versions: Ruff 0.16.5, mypy 1.20.2, pytest 9.1.1. The suite has no paid calls,
API keys, provider SDKs, or network-service dependency. CI is configured to run the
same commands; dependency installation downloads packages. Remote CI status is
separate from these local results and is not fabricated here.

## Files changed

The following inventory includes the previously uncommitted Stage 1 foundation
that must accompany this Stage 2 delivery. Paths are relative to the repository.

```text
.github/workflows/ci.yml
.gitignore
README.md
pyproject.toml
docs/STAGE_1_REPORT.md
docs/STAGE_2_REPORT.md
docs/architecture/ADR/ADR-004-implementation-language.md
docs/architecture/ADR/ADR-005-single-agent-runtime.md
docs/architecture/AGENT_RUNTIME_ARCHITECTURE.md
docs/engineering/DEVELOPMENT_ROADMAP.md
docs/engineering/EVALUATION_STRATEGY.md
docs/engineering/TESTING_STRATEGY.md
docs/project/GLOSSARY.md
src/agent_company_os/__init__.py
src/agent_company_os/py.typed
src/agent_company_os/serialization.py
src/agent_company_os/domain/__init__.py
src/agent_company_os/domain/ids.py
src/agent_company_os/domain/errors.py
src/agent_company_os/domain/validation.py
src/agent_company_os/domain/workspace.py
src/agent_company_os/domain/goal.py
src/agent_company_os/domain/task.py
src/agent_company_os/domain/task_attempt.py
src/agent_company_os/domain/execution.py
src/agent_company_os/domain/events.py
src/agent_company_os/domain/transitions.py
src/agent_company_os/domain/agent.py
src/agent_company_os/domain/decisions.py
src/agent_company_os/application/__init__.py
src/agent_company_os/application/service.py
src/agent_company_os/application/context.py
src/agent_company_os/application/research_agent.py
src/agent_company_os/application/runtime.py
src/agent_company_os/application/runtime_serialization.py
src/agent_company_os/ports/__init__.py
src/agent_company_os/ports/clock.py
src/agent_company_os/ports/ids.py
src/agent_company_os/ports/store.py
src/agent_company_os/ports/model.py
src/agent_company_os/ports/runtime_store.py
src/agent_company_os/adapters/__init__.py
src/agent_company_os/adapters/clocks.py
src/agent_company_os/adapters/ids.py
src/agent_company_os/adapters/in_memory.py
src/agent_company_os/adapters/fake_model.py
src/agent_company_os/adapters/runtime_store.py
tests/conftest.py
tests/test_application.py
tests/test_state_machines.py
tests/test_serialization.py
tests/test_store_guards.py
tests/test_runtime.py
tests/fixtures/agent_eval/cases.json
```

## Architecture changes

[ADR-005](architecture/ADR/ADR-005-single-agent-runtime.md) records standalone AgentRun,
the strict internal decision protocol, extractive completion, bounded wait/resume,
and shared rollback boundary. ADR-001–004 accepted decisions are preserved. There
is no blanket DomainService decomposition; the new runtime has its own responsibility
and store port. Events remain audit facts, not an event-sourcing architecture.

## Completion criteria

All mandatory deterministic Stage 2 criteria pass: verified Stage 1 gate, versioned
definition/history, AgentRun, provider-neutral port and fake, typed requests and
decisions, output validation, Action/Observation separation, bounded WorkingState
and context, iteration/timeouts, deterministic authorization/completion, wait/resume,
events, workspace/version guards, one agent, adversarial/eval fixtures, passing
integration/lint/type checks, offline test-phase CI, and this report. Live provider
integration is optional and explicitly deferred. No multi-agent capability is claimed.

## Deferred work and open questions

- Which live provider/model and calibrated semantic evaluator meet quality needs?
- How should authenticated callers approve context and revoke definition/policy use?
- What source snapshot/retention policy preserves every historical model request?
- When are durable storage, recovery of claimed invocations, and expiry scheduling required?
- Which deployment/version identifier should accompany semantic protocol versions?
- How should future cancellation coordinate remote provider work and tool receipts?

In-memory snapshot transactions are not durable or production-load infrastructure.
There is no automatic crashed-process recovery and no general sandbox.

## Explicitly not implemented

Tool Runtime, web search, filesystem/database/API action executors, external write
actions, MCP, RAG, embeddings, knowledge retrieval, Company Brain, long-term/episodic/
semantic Memory, multi-agent delegation, Chief of Staff, handoffs, agent messaging,
autonomous Level 3/4 behavior, graph/org UI, or production queue infrastructure.

## Recommended Stage 3

Recommend **Tool Runtime**, initially with bounded read-only fixtures, typed
permissions/receipts, idempotency, and failure reconciliation. Stage 2 now provides
the verified schema/policy/version/timeout/atomic-completion boundary into which
those capabilities could be added. This is not evidence that external actions are
already safe. Stage 3 has not been started.
