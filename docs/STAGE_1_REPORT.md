# Stage 1 Verification Record

## Outcome and provenance

Reconstructed on 2026-09-03 from the actual local implementation during the
Stage 2 cleanup gate. Stage 1 had not previously produced a report or completed
verification. This is not a claim that checks passed on an earlier date.

Python 3.13 implements Workspace, Goal, Task, TaskAttempt, Execution, immutable
StateTransition records, and versioned Event records. See
[ADR-004](architecture/ADR/ADR-004-implementation-language.md).

## Technology and boundaries

Standard-library runtime; Ruff formatter/linter, strict mypy, pytest, and GitHub
Actions configuration. The application uses typed creation commands and methods,
Clock, IdGenerator, and DomainStore ports. SystemClock/FakeClock,
SystemIdGenerator/DeterministicIdGenerator, and InMemoryDomainStore implement them.
No database, queue, model dependency, or production infrastructure was selected.

## State machines

- Goal: draft, active, satisfied, closed_unsatisfied, cancelled.
- Task: proposed, ready, in_progress, blocked, completed, failed, cancelled.
- TaskAttempt: created, running, succeeded, failed, cancelled.
- Execution: created, running, waiting, succeeded, failed, cancelled.

Edges follow ADR-002. Timeout is a failure reason. Duplicate terminal completion
raises an explicit error. Retry creates a linked new attempt; historical outcomes
are not overwritten. Satisfaction remains an explicit application command.

## Invariants and corrections

Differentiated IDs, positive versions, UTC clock validation, immutable entities,
legal transitions, stale-version rejection, workspace relationships, bounded
attempt counts, and one non-terminal attempt per Task are implemented.

The cleanup gate corrected an incorrect demo assertion (21 Events and 14
transitions, not 19 and 12), formatting/lint issues, and untyped test helpers.
Persistence now rejects mismatched audit subjects/workspaces, illegal transitions,
and changes to immutable historical fields. Attempt uniqueness/lineage/bounds are
checked inside the store lock. A rollback transaction boundary was added for
subsequent multi-record runtime changes. Five regression tests were added.

## Actual verification before Stage 2 runtime code

Initial run: pytest **45 passed, 1 failed**; mypy passed for 27 files;
Ruff reported 11 lint errors and 13 unformatted files.

After cleanup:

```text
python -m ruff format --check src tests: 28 files already formatted
python -m ruff check src tests: All checks passed!
python -m mypy: Success: no issues found in 28 source files
python -m pytest -q: 51 passed in 0.14s
```

These commands used `.venv/Scripts/python.exe`. CI is configured but has not
been run remotely as part of this verification. Dependency installation requires
network access; the test suite itself requires no network, secrets, or paid APIs.

## Deterministic demo

`tests/test_application.py::test_deterministic_end_to_end_scenario` creates a
Workspace and Goal, activates the Goal, creates two Tasks, starts an Execution,
runs and accepts each TaskAttempt, completes each Task, explicitly succeeds the
Execution, and explicitly satisfies the Goal. IDs/time and audit ordering are
deterministic. All legal lifecycle edges and representative illegal paths are tested.

## Files

- Tooling: `pyproject.toml`, `.gitignore`, `.github/workflows/ci.yml`.
- Package: `src/agent_company_os/__init__.py`, `py.typed`, `serialization.py`.
- Domain: `domain/__init__.py`, `ids.py`, `errors.py`, `validation.py`,
  `workspace.py`, `goal.py`, `task.py`, `task_attempt.py`, `execution.py`,
  `events.py`, `transitions.py`.
- Application: `application/__init__.py`, `service.py`.
- Ports: `ports/__init__.py`, `clock.py`, `ids.py`, `store.py`.
- Adapters: `adapters/__init__.py`, `clocks.py`, `ids.py`, `in_memory.py`.
- Tests: `conftest.py`, `test_application.py`, `test_state_machines.py`,
  `test_serialization.py`, `test_store_guards.py`.
- Documentation: ADR-004 and this report; current README/roadmap status is updated
  by the Stage 2 delivery rather than rewriting earlier reports.

## Deferred work and limits

No AI, AgentRun, Action/Observation families, LLM calls, providers, tools, RAG,
embeddings, retrieval, memory, orchestration, MCP, integrations, UI, or autonomous
external actions existed at this gate. AgentDefinition/version types were deferred
until a runtime actually needs them. In-memory persistence is not durable, and
the library is not an authenticated API. Production tenancy/authentication,
durability, retention, and distributed coordination remain future work.

## Next stage

The verified deterministic foundation is ready for the requested Stage 2
single-agent runtime. This report does not certify probabilistic answer quality.
