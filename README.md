# Agent Company OS

**Current Stage: Stage 3 — Tool Runtime (offline read-only fixture verification)**

Agent Company OS is a working title for a production-oriented platform for operating an AI-native organization. It is intended to coordinate goals, specialized agents, deterministic workflows, governed tools, shared knowledge, human approvals, and auditable execution—without reducing the product to a collection of chatbots.

## Why it exists

Current AI assistants are often isolated, difficult to govern, weakly observable, and hard to reuse. Agent Company OS aims to provide explicit organizational, runtime, permission, and evaluation structures so that useful autonomy can be introduced safely.

## High-level architecture

The conceptual system separates application, runtime, policy, and persistence boundaries. The implemented slice uses Python 3.13, immutable domain entities, typed ports, in-memory adapters, one bounded single-agent loop, and two read-only fixture tools. Knowledge retrieval, memory, and multi-agent orchestration remain future work. See [System Architecture](docs/architecture/SYSTEM_ARCHITECTURE.md) and [Domain Model](docs/architecture/DOMAIN_MODEL.md).

## Documentation map

- [Product requirements](docs/product/PRD.md), [personas](docs/product/PERSONAS.md), [user journeys](docs/product/USER_JOURNEYS.md), [MVP scope](docs/product/MVP_SCOPE.md), and [success metrics](docs/product/SUCCESS_METRICS.md)
- [Architecture](docs/architecture/SYSTEM_ARCHITECTURE.md), [runtime](docs/architecture/AGENT_RUNTIME_ARCHITECTURE.md), [data](docs/architecture/DATA_ARCHITECTURE.md), [security](docs/architecture/SECURITY_AND_PERMISSIONS.md), [ADR-001](docs/architecture/ADR/ADR-001-architecture-principles.md), [ADR-002](docs/architecture/ADR/ADR-002-execution-domain-semantics.md), and [ADR-003](docs/architecture/ADR/ADR-003-agent-definition-and-runtime-identity.md)
- [Engineering principles](docs/engineering/ENGINEERING_PRINCIPLES.md), [roadmap](docs/engineering/DEVELOPMENT_ROADMAP.md), [testing](docs/engineering/TESTING_STRATEGY.md), [evaluation](docs/engineering/EVALUATION_STRATEGY.md), [observability](docs/engineering/OBSERVABILITY_STRATEGY.md), and [risk register](docs/engineering/RISK_REGISTER.md)
- [Glossary](docs/project/GLOSSARY.md), [assumptions](docs/project/ASSUMPTIONS.md), [open questions](docs/project/OPEN_QUESTIONS.md), [Stage 0 report](docs/STAGE_0_REPORT.md), and [Stage 0.1 refinement report](docs/STAGE_0_1_REFINEMENT_REPORT.md)

## Development philosophy

Build trust and visibility before autonomy. Keep state explicit, boundaries typed, permissions least-privileged, model outputs validated, and deterministic work deterministic. Treat failure, approval, auditability, and evaluation as runtime concerns rather than UI afterthoughts.

## Current status and next milestone

Stage 1 implements deterministic Workspace/Goal/Task/TaskAttempt/Execution state,
version guards, and audit history. Stage 2 adds immutable AgentDefinition versions,
AgentRun, structured decisions, internal Actions/Observations, policy validation,
bounded working state, and wait/resume. Stage 3 adds exact-version tool grants,
Company Fact Lookup and Source Fact Lookup, strict validation, bounded execution,
immutable receipts, and grounded tool Observations. The Research Brief Agent can
optionally use these tools. Its model adapter remains scripted, not a live AI model.

Read [Stage 1 verification](docs/STAGE_1_REPORT.md), [Stage 2 report](docs/STAGE_2_REPORT.md),
[language decision](docs/architecture/ADR/ADR-004-implementation-language.md), and
[runtime decision](docs/architecture/ADR/ADR-005-single-agent-runtime.md).
Read the [Stage 3 report](docs/STAGE_3_REPORT.md) and
[Tool Runtime decision](docs/architecture/ADR/ADR-006-tool-runtime.md).
No paid calls or credentials are required. No external write tools, live network
adapter, RAG, Memory, MCP, multi-agent system, UI, or production persistence exists.

## Development

Python 3.13, from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest -q
```

On macOS/Linux use `.venv/bin/python` instead. Installation downloads development
dependencies; the suite itself is offline, deterministic, and secret-free.
Run `python -m pytest tests/test_runtime.py -q` in the activated environment for
the single-agent demo/failure suite. `test_grounded_completion_fixtures` proves
completion; `test_wait_supply_resume_same_identity` proves context resumption.

Run `python -m pytest tests/test_tools.py -q` for the tool-use scenarios, race tests,
and adversarial fixtures. Defaults: 5 tool calls/run, 3/tool, 3 seconds/tool,
2,048 input bytes, 8,192 output bytes, and no automatic retry; existing iteration
and run-deadline limits also apply. Receipts prove observed data, not source truth.

The next proposed milestone is **Stage 4: Company Brain / Knowledge Retrieval**.
It has not been started. Passing offline tests does not establish live-model quality
or production readiness.
