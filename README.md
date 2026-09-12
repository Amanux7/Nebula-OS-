# Agent Company OS

### A governed runtime for AI-native work

[![CI](https://github.com/Amanux7/Nebula-OS-/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Amanux7/Nebula-OS-/actions/workflows/ci.yml)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Turn business goals into bounded, inspectable work—with explicit state, narrowly
scoped capabilities, and evidence behind every accepted result.

> **AI for judgment. Software for guarantees.**

**Current milestone: Stage 9 — Human Approval and Consequential Action Governance.** The
repository implements a deterministic domain foundation, a bounded single-agent
runtime, controlled read-only tools, source-aware Knowledge, reviewed scoped Memory,
replaceable orchestration, and governed point-to-point communication with explicit
handoffs and reference re-authorization. A versioned organization now provides
department, role, and capability discovery with explicit routing restrictions.
Exact action intents, single-use human approvals, and bounded autonomy now govern
one offline write-style fixture, with current-state revalidation before dispatch.
It is an early-stage engineering foundation,
not a deployed autonomous company or a production-ready AI service.

[Get started](#getting-started) · [Architecture](#architecture) ·
[Execution flow](#tool-execution-flow) · [Roadmap](#roadmap) ·
[Documentation](#documentation) · [Contribute](#contributing)

---

## About the project

Agent Company OS is the working product name for the project in the **Nebula-OS-**
repository. Its mission is to make AI-assisted business work accountable: define
the outcome, constrain the work, control access, preserve evidence, and let people
inspect what happened.

The long-term vision is an operating layer for an AI-native organization—not a
collection of disconnected chatbots. Specialized agents and deterministic workflows
would share governed company knowledge, collaborate on bounded tasks, and escalate
consequential decisions to people. Those organizational capabilities are a roadmap,
not a claim about the current implementation.

| Project information | Details |
|---|---|
| Working product name | Agent Company OS |
| Repository | [Amanux7/Nebula-OS-](https://github.com/Amanux7/Nebula-OS-) |
| Repository owner | [Amanux7](https://github.com/Amanux7) |
| License | [MIT](LICENSE) |
| Current focus | Bounded planning, deterministic delegation, safe execution, evidence, provenance, and verification |
| Intended users | Founders, startup teams, operations leaders, automation builders, agencies, and SMBs |
| Reference workflow | Evidence-backed research and structured business briefs |

These users and workflows are product hypotheses under validation. See the
[PRD](docs/product/PRD.md) and [personas](docs/product/PERSONAS.md) for the product
context; no commercial traction or incorporated-company status is implied.

## Why this exists

Useful automation needs more than a capable model. It needs clear answers to:

- **Authority:** Which operations may this agent request, in this workspace?
- **State:** What is running, waiting, completed, failed, or cancelled?
- **Evidence:** Which inputs, versions, and observed results support the output?
- **Control:** What prevents duplicate execution, stale updates, or unbounded loops?
- **Recovery:** What remains inspectable when a model, tool, or persistence step fails?

Agent Company OS makes those questions software responsibilities. A model proposal
cannot grant permissions, bypass domain invariants, or certify its own success.

## What works today

| Capability | Implemented behavior |
|---|---|
| Deterministic domain | Workspace, Goal, Task, TaskAttempt, and Execution lifecycles with typed errors and version guards |
| Configuration history | Immutable AgentDefinition versions bound to each AgentRun |
| Single-agent runtime | Structured decisions, bounded working state, wait/resume, cancellation, and a scripted FakeModel |
| Controlled tools | Exact-version registry, explicit grants, read-only risk enforcement, strict inputs and outputs |
| Execution evidence | Immutable ToolReceipts, typed Observations, audit Events, and explicit receipt export |
| Company Brain | Versioned text/Markdown/structured facts, source grants, lexical retrieval, and immutable EvidencePacks |
| Governed Memory | Host-derived candidates, mandatory human review, scoped Episodic/Semantic entries, lifecycle controls, and immutable MemoryContextPacks |
| Replaceable orchestration | Validated immutable plan versions, one-time materialization, dependency readiness, deterministic agent selection, bounded replan/retry/delegation, and explicit result lineage |
| Governed communication | Typed point-to-point messages, exact correlation and participant versions, recipient-scoped references, bounded context, and orchestration-mediated handoffs |
| Grounded completion | Exact findings checked against supplied facts, successful tool receipts, or active same-run knowledge evidence |
| Failure handling | Timeouts, budgets, duplicate-invocation protection, stale-result rejection, and atomic rollback |
| Organization | Immutable graph versions, effective memberships, governed reporting, registry discovery, and department policy |
| Governance | Exact payload fingerprints, explicit reviewers, expiry/revocation, one-use approval, and bounded Level 3 fixture execution |
| Verification | 444 passing tests at the Stage 9 gate, plus formatting, lint, and strict type checks |

The only supplied agent type is the **Research Brief Agent**. It can operate on
approved supplied facts or receive an immutable definition upgrade granting the
two fixture tools and/or a fixed knowledge-source allowlist. Its model responses are
scripted; no live LLM provider is wired in.

## Architecture

The implemented architecture is a **modular Python application**, not a microservice
deployment. These are logical responsibilities, not separately deployed services.

~~~mermaid
flowchart TD
    caller["Application caller or tests"] --> domainService["DomainService"]
    caller --> agentRuntime["AgentRuntimeService"]
    caller --> orchestrator["OrchestrationService"]
    orchestrator -->|"OrchestrationStrategyPort"| planner["Deterministic or fake strategy"]
    orchestrator -->|"Validate + materialize"| domainService
    orchestrator -->|"Select eligible definition"| selector["AgentSelector"]
    orchestrator -->|"Delegate ready task"| agentRuntime
    communication["AgentCommunicationService"] -->|"Typed message context"| agentRuntime
    communication -->|"Validated handoff request"| orchestrator
    agentRuntime -->|"Domain commands"| domainService
    domainService -->|"Enforces invariants"| domain["Typed domain entities"]
    agentRuntime -->|"ModelPort"| model["Scripted FakeModel"]
    agentRuntime -->|"ToolRuntimePort"| toolRuntime["ToolRuntimeService"]
    agentRuntime -->|"KnowledgeRuntimePort"| knowledge["KnowledgeService"]
    agentRuntime -->|"MemoryRuntimePort"| memory["MemoryService"]
    toolRuntime -->|"Resolve exact grants"| registry["ToolRegistry"]
    toolRuntime -->|"ToolExecutor"| fixtures["Read-only fixture tools"]
    domainService -->|"DomainStore"| state["In-memory domain state"]
    agentRuntime -->|"RuntimeStore"| history["In-memory runtime records"]
    toolRuntime -->|"Claims and receipts"| history
    knowledge -->|"EvidencePack"| history
    memory -->|"MemoryContextPack"| history
    orchestrator -->|"Plans, delegations, lineage"| orchestrationHistory["In-memory orchestration records"]
    orchestrationHistory ---|"Shared rollback boundary"| state
    history ---|"Shared rollback boundary"| state
~~~

### Separation of responsibilities

- **Domain:** legal lifecycles, entity relationships, workspace scope, and historical integrity.
- **Application:** domain use cases, agent coordination, context assembly, grounding, and tool execution policy.
- **Ports:** typed seams for clocks, identifiers, models, tools, registries, and storage.
- **Adapters:** in-memory persistence, system/test clocks and IDs, scripted models, and fixture executors.

AgentRuntimeService coordinates decisions; ToolRuntimeService controls capabilities.
Neither model text nor tool-returned content becomes an authority boundary.
Canonical state is stored directly, with append-only history—it is **not event sourcing**.

### Company Brain boundary

The host calls `KnowledgeService` to publish approved source versions, disable sources,
or retrieve a bounded EvidencePack for an idle AgentRun. `KnowledgeIngestor`,
`KnowledgeRetriever`, and `KnowledgeStore` separate ingestion, ranking, and persistence.
The runtime reads authorized packs through `KnowledgeRuntimePort`; retrieval is not
registered as a tool and does not add another agent action or planner.

Publication produces immutable normalized source versions and deterministic chunks.
Source grants and trust filters are applied before lexical ranking. The exact returned
chunks, versions, hashes, trust labels, query, and strategy become an immutable pack.
Context assembly keeps it separate from supplied data and tool Observations. Model
completion must cite exact structured facts from the active same-run pack; free-text
paraphrases are not treated as verified facts. Replacing context does not erase history.

Default bounds: 32 KiB/source, 800 characters/chunk, 5 candidates/query, a 4,000-character
serialized pack, 2 candidates/source, and 5 packs/run. The existing total context cap
still applies. See [ADR-007](docs/architecture/ADR/ADR-007-company-brain-and-knowledge-retrieval.md)
for all hard limits, historical-version policy, revocation, and grounding limitations.

### Governed Memory boundary

Memory is retained experience, not authoritative Knowledge. Trusted host code derives
a bounded candidate from canonical successful-run references. Deterministic policy
rejects unsupported model inference, Knowledge duplication, and detectable secrets;
every eligible candidate then requires explicit human approval. Promotion creates an
immutable-content entry that can later be revoked, superseded, or excluded by expiry.

~~~mermaid
flowchart LR
    source["Successful AgentRun sources"] --> candidate["MemoryCandidate"]
    candidate --> policy{"Policy"}
    policy -->|"reject"| rejected["Rejected + audited"]
    policy -->|"review"| review{"Human review"}
    review -->|"reject"| rejected
    review -->|"approve"| entry["Active MemoryEntry"]
    entry --> filter["Exact scope + sensitivity + lifecycle filters"]
    filter --> pack["Immutable MemoryContextPack"]
    pack --> model["Separate model context"]
    knowledge2["Authoritative Knowledge"] --> evidence["Grounding evaluator"]
    model -.->|"Memory cannot ground"| evidence
~~~

Retrieval uses exact subject matching and deterministic lexical ranking under explicit
AgentDefinitionVersion grants. The runtime revalidates packs before and after model
invocation. Conflicts are retained and labeled; Knowledge keeps precedence because
Memory is never accepted by the completion evidence evaluator. See
[ADR-008](docs/architecture/ADR/ADR-008-governed-memory.md).

### Orchestration and delegation boundary

`OrchestrationService` turns an active Goal into a bounded, validated plan without
giving the planner authority over canonical state. A replaceable strategy returns an
untrusted proposal; deterministic validation enforces workspace, size, dependency,
depth, eligibility, and policy limits before creating an immutable `PlanVersion`.
Materialization creates canonical Tasks exactly once. Readiness is derived from
completed dependencies, and deterministic selection binds each delegation to an exact
published `AgentDefinitionVersion` before the existing `AgentRuntimeService` executes it.

~~~mermaid
flowchart LR
    goal["Active Goal"] --> strategy["Replaceable strategy"]
    strategy --> proposal["Untrusted PlanProposal"]
    proposal --> validation{"Domain + policy validation"}
    validation -->|"reject"| waiting["Failed or waiting with reason"]
    validation -->|"accept"| version["Immutable PlanVersion"]
    version --> tasks["One-time canonical Task materialization"]
    tasks --> ready{"Dependencies complete?"}
    ready -->|"yes"| selection["Deterministic eligible-agent selection"]
    selection --> delegation["Delegation with exact version lineage"]
    delegation --> runtime["Existing AgentRuntimeService"]
    runtime --> result["TaskResultReference"]
    result --> aggregate["Structural completion validation"]
~~~

Planning is replaceable; the planner cannot create permissions, bypass Task state,
or certify Goal success. Replanning preserves immutable history and cannot remove
already materialized work in Stage 6. The implementation is synchronous and in-memory;
it is not a durable workflow engine, queue, multi-agent chat system, or live-model
planner. See [ADR-009](docs/architecture/ADR/ADR-009-replaceable-orchestration-and-delegation.md).

### Multi-agent communication and handoffs

Active participants in the same OrchestrationRun may exchange typed, bounded
point-to-point messages when both exact AgentDefinitionVersions opt in and deterministic
role policy permits the recipient. Requests and responses carry explicit correlation;
all sender/recipient, Task, Delegation, policy, schema, and provenance versions remain
historical. References to Task results, tool receipts, Knowledge, or Memory are checked
again against the recipient's own grants before delivery.

A substantial-work request becomes a `HandoffRequest`, not hidden message work. The
existing selector and orchestrator resolve it into a normal redelegation, and completion
links to the resulting canonical TaskResultReference. Messages enter model input through
a separate bounded `agent_messages` section labeled as untrusted agent content; they do
not grant tools, become Knowledge, auto-promote to Memory, or ground completion.

The default is direct in-process delivery: no broadcast, pub/sub, inbox polling, shared
blackboard, message broker, external provider, or free-form chat. See
[ADR-010](docs/architecture/ADR/ADR-010-multi-agent-communication-and-handoffs.md).

The [System Architecture](docs/architecture/SYSTEM_ARCHITECTURE.md) describes the
broader target design. Its multi-agent communication, organization UI, approval,
external integration, and production infrastructure layers must not be mistaken for
implemented services.

### Domain vocabulary

| Concept | Meaning |
|---|---|
| Goal | A desired outcome, not an implementation step |
| Task | Bounded logical work contributing to a Goal |
| TaskAttempt | One attempt to perform a Task; retries preserve prior history |
| Execution | A bounded root attempt containing task execution activity |
| AgentDefinitionVersion | Immutable behavior and capability configuration |
| AgentRun | Runtime participation of that exact configuration for a TaskAttempt |
| Action | A requested operation—not proof that it happened |
| Observation | Information returned to the runtime, with provenance and trust |
| ToolReceipt | Immutable evidence of what a tool invocation returned or how it failed |
| MemoryCandidate | Host-derived proposal that policy rejects or sends to human review |
| MemoryEntry | Reviewed retained experience with immutable content/provenance |
| MemoryContextPack | Exact bounded memory snapshot for one run; never grounding evidence |
| PlanVersion | Immutable accepted plan snapshot with ordered tasks, dependencies, policy, and lineage |
| OrchestrationRun | Bounded coordinator state for planning, materialization, delegation, and completion |
| Delegation | Assignment of one canonical Task to one exact AgentDefinitionVersion |
| TaskResultReference | Exact successful TaskAttempt/AgentRun result lineage used by downstream work |
| AgentMessage | Immutable typed point-to-point envelope with exact participant lineage |
| HandoffRequest | Governed request for substantial-work transfer through orchestration |

See the [Domain Model](docs/architecture/DOMAIN_MODEL.md) and
[Glossary](docs/project/GLOSSARY.md) for complete definitions.

## Tool execution flow

The model requests a capability; deterministic software decides whether it runs.
This flow shows the tool branch of the agent loop. Schema or runtime faults and
exhausted limits use the runtime's failure path rather than continuing indefinitely.

~~~mermaid
flowchart TD
    proposal["Structured call_tool Action"] --> gate{"Authorized and valid?"}
    gate -->|"No"| rejected["Record rejection Observation"]
    gate -->|"Yes, within limits"| claim["Persist invocation claim"]
    claim --> execute["Execute outside transaction lock"]
    execute --> check["Validate result and current state"]
    check --> current{"Current and active?"}
    current -->|"No"| stale["Audit discarded late result"]
    current -->|"Yes"| receipt["Commit success or failure receipt"]
    receipt --> observation["Create bounded Observation"]
    observation --> nextDecision["Next model decision"]
    rejected --> nextDecision
    nextDecision --> completion{"Proposes completion?"}
    completion -->|"Yes"| grounding{"Grounding passes?"}
    grounding -->|"Yes"| completed["Commit validated completion"]
    grounding -->|"No"| failed["Reject unsupported completion"]
    completion -->|"No"| continueRun["Continue or wait within limits"]
~~~

Successful tool execution does **not** automatically complete the Task. A subsequent
`complete_task` decision must pass grounding and domain validation. Goal satisfaction
is a separate explicit operation.

### Current tool catalog

| Tool | Input | Result |
|---|---|---|
| Company Fact Lookup | `company_name` | Approved fixture facts for that company |
| Source Fact Lookup | `source_id` and unique `keys` | Matching approved source facts |
| Send Fixture Message | Exact `destination` and `message` | Governed local fixture delivery and observed receipt; no real message sent |

The two lookups are read-only; all three capabilities are deterministic and offline.
The write-style fixture requires an independent Tool grant plus exact approval at
Level 2, or explicit bounded policy at Level 3. A fake executor additionally supports
scripted errors, timeouts, blocked calls, and captured inputs for tests.

### Consequential-action governance

A validated Tool proposal becomes an immutable ActionIntent bound to its actor,
workspace, exact tool version, destination, payload fingerprint, risk, and policy.
Human approval applies to that intent only. Before dispatch the runtime rechecks
current policy, expiry, revocation, grants, organization, and active work. It reserves
the intent with the ToolInvocation claim, preventing duplicate dispatch.

Approval waits preserve the same work identity, deadline, and budgets. Rejection
performs no write; timeout or cancellation after dispatch never proves no write occurred.
Managers are not automatic approvers, and Level 4/high-risk actions remain denied.
See [ADR-012](docs/architecture/ADR/ADR-012-human-approval-autonomy-and-consequential-actions.md)
and the [Stage 9 report](docs/STAGE_9_REPORT.md) for exact guarantees and limitations.

### Safety defaults

| Control | Default |
|---|---|
| Model iterations | 5 per run |
| Total run deadline | 60 seconds |
| Model timeout | 5 seconds per call |
| Tool budget | 5 calls per run; 3 per tool |
| Tool timeout | 3 seconds, capped by the remaining run deadline |
| Tool payloads | 2,048 input bytes; 8,192 output bytes |
| Automatic retries | Disabled |
| Context | Last 4 Observations; 16,000 text characters |
| Receipt preview | Up to 5 facts per Observation; up to 10 in the canonical receipt |

Each tool request consumes a model iteration. Using all five default iterations on
tools leaves no iteration for completion. Limits remain in force across wait/resume.

Exact replay of the same host-generated Action does not execute its tool again.
A deliberate new Action with the same arguments is a new budgeted invocation.
This is local idempotency, not distributed exactly-once execution.

## Getting started

### Prerequisites

- Git and Python **3.13** for the tested development environment.
- No API keys, database, containers, or external services are needed to run the tests.
- Installing development dependencies requires package-download access.

Clone the repository:

~~~bash
git clone https://github.com/Amanux7/Nebula-OS-.git
cd Nebula-OS-
~~~

**Windows / PowerShell**

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
~~~

**macOS / Linux**

~~~bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
~~~

There is no web server, dashboard, or deployment command in this stage. The
executable entry points are the typed application services and integration tests.

### Run the deterministic demos

Using the virtual environment's Python executable:

~~~bash
python -m pytest tests/test_runtime.py -q
python -m pytest tests/test_tools.py -k deterministic_tool_eval -v
~~~

On Windows, substitute `.\.venv\Scripts\python.exe` for `python`; on macOS/Linux,
use `.venv/bin/python`, unless the virtual environment is already activated.

The tool scenarios create a Workspace, Goal, Task, Execution, and TaskAttempt; start
the Research Brief Agent; execute permitted fixture lookups; record receipts; and
validate an explicit completion decision. Companion cases cover no-tool-needed,
repeated-read, and two-tool behavior. No live model or network call is made.

## Development and quality gates

Run all checks with the virtual environment's Python:

~~~bash
python -m ruff format --check src tests
python -m ruff check src tests
python -m mypy
python -m pytest -q
git diff --check
~~~

The existing [GitHub Actions workflow](.github/workflows/ci.yml) runs formatting,
lint, type checking, and tests on pushes and pull requests. The test phase is offline
and secret-free; dependency installation still uses package downloads. The CI badge
above tracks `main`, not unmerged pull-request branches.

### Review workflow

Changes are developed on focused `codex/*` branches and reviewed through GitHub pull
requests. Each pull request should include a concise scope statement, linked ADRs or
requirements for architectural changes, deterministic test evidence, security and
data-boundary notes, and explicit deferred work. Reviewers can reproduce the local gate
with the commands above; CI repeats the same checks without secrets, paid APIs, live
models, or external services.

Use the repository's [open pull requests](https://github.com/Amanux7/Nebula-OS-/pulls)
page to review published changes. The [Stage 9 report](docs/STAGE_9_REPORT.md)
summarizes the current local implementation, verification results, risks, and deferred work.

The [Stage 7 report](docs/STAGE_7_REPORT.md) records **331 passing tests**, including
the A–AD communication/handoff matrix and Stage 6 review regression cases. Passing
scripted tests establishes software behavior—not live-model planning, communication
usefulness, or answer quality.

The Stage 8 gate extends that baseline to 386 passing tests. Stage 9 adds 58 governance
cases, for **444 passing tests**, including exact approval, organization-aware
wait/resume, rejection, replay, rollback, and uncertain-outcome scenarios.

Run the Company Brain scenarios alone with `python -m pytest tests/test_knowledge.py -q`.
The fictional Aurora Desk corpus demonstrates missing-context recovery, version updates,
conflicting prices, unauthorized sources, injected instructions, forged references,
bounded retrieval, and combined knowledge/tool evidence without network calls.

## Repository structure

~~~text
.
├── src/agent_company_os/
│   ├── domain/              # Entities, value objects, state and evidence contracts
│   ├── application/         # Domain, agent, tool, knowledge, memory and orchestration services
│   ├── ports/               # Typed runtime, strategy, policy, ID and storage boundaries
│   ├── adapters/            # In-memory stores, deterministic strategies and scripted doubles
│   └── serialization.py     # Explicit domain boundary serialization
├── tests/
│   ├── fixtures/agent_eval/ # Deterministic and adversarial evaluation fixtures
│   ├── test_runtime.py      # Single-agent scenarios and failure paths
│   ├── test_tools.py        # Tool contracts, safety, provenance and race tests
│   └── test_orchestration.py # Stage 6 planning and delegation scenarios
├── docs/
│   ├── product/             # Requirements, personas, scope and success criteria
│   ├── architecture/        # Domain, runtime, security and architecture decisions
│   ├── engineering/         # Roadmap, testing, evaluation and observability
│   └── project/             # Glossary, assumptions and open questions
├── .github/workflows/ci.yml
├── pyproject.toml
└── LICENSE
~~~

## Roadmap

| Stage | Focus | Status |
|---|---|---|
| 0 | Product and architecture foundation | Documented |
| 0.1 | Execution semantics and architectural refinement | Documented |
| 1 | Deterministic domain foundation | Implemented and verified |
| 2 | Single-agent runtime | Verified with a scripted model |
| 3 | Controlled read-only Tool Runtime | Implemented and verified offline |
| 4 | Company Brain / Knowledge Retrieval | Implemented and verified offline |
| 5 | Governed Memory | Implemented and verified offline |
| 6 | Replaceable orchestration and delegation | Implemented and verified offline |
| 7 | Multi-agent communication and handoffs | Implemented and verified offline |
| 8 | Departments, registry, and organization graph | Implemented and verified offline |
| 9 | Human approval and consequential-action governance | Implemented and verified offline |
| 10 | Reliability, recovery, and audit-query foundations | Recommended next; not started |
| Later | Observability/approval UI, evaluations, integrations, and production | Deferred pending evidence |

Stages are evidence gates, not release dates. Planning may eventually be deterministic,
agentic, or hybrid; Stage 6 selects a replaceable seam and deterministic baseline, not
a general planner model or agent framework.
See the [Development Roadmap](docs/engineering/DEVELOPMENT_ROADMAP.md).

## Security and known limitations

- **No production external writes:** no email, Slack, database mutation, shell, filesystem,
  browser, payment, or purchase tools are implemented.
- **No live AI or integrations:** no live model provider, OAuth connector, or MCP runtime.
- **Knowledge is a lexical baseline:** no embeddings, semantic ranking, automatic
  crawling or generic document parser. Memory and communication are separate governed capabilities.
- **In-memory persistence:** history disappears on process exit; durable recovery
  and production retention/deletion policies remain unresolved.
- **Cooperative adapters:** async timeouts require nonblocking, cancellation-aware
  executors. The runtime is not a sandbox for hostile Python code.
- **Provenance is not truth:** receipts establish observed inputs and outputs,
  not source correctness, freshness, or semantic entailment.
- **Trusted application callers:** reviewer identity is explicit but not production-authenticated.
  Governance covers one fixture capability, not production security or distributed exactly-once writes.

Tool output and retrieved text are data, never instructions to broaden authority. Credentials must
remain outside model context when future integrations are introduced. Read the
[security architecture](docs/architecture/SECURITY_AND_PERMISSIONS.md),
[risk register](docs/engineering/RISK_REGISTER.md), and
[open questions](docs/project/OPEN_QUESTIONS.md) before extending the runtime.

## Documentation

| Start here | References |
|---|---|
| Product and company vision | [PRD](docs/product/PRD.md), [MVP scope](docs/product/MVP_SCOPE.md), [user journeys](docs/product/USER_JOURNEYS.md), [success metrics](docs/product/SUCCESS_METRICS.md) |
| Domain and system design | [Domain Model](docs/architecture/DOMAIN_MODEL.md), [System Architecture](docs/architecture/SYSTEM_ARCHITECTURE.md), [Agent Runtime](docs/architecture/AGENT_RUNTIME_ARCHITECTURE.md), [Data Architecture](docs/architecture/DATA_ARCHITECTURE.md) |
| Engineering standards | [Principles](docs/engineering/ENGINEERING_PRINCIPLES.md), [testing](docs/engineering/TESTING_STRATEGY.md), [evaluation](docs/engineering/EVALUATION_STRATEGY.md), [observability](docs/engineering/OBSERVABILITY_STRATEGY.md) |
| Shared terminology | [Glossary](docs/project/GLOSSARY.md), [assumptions](docs/project/ASSUMPTIONS.md), [open questions](docs/project/OPEN_QUESTIONS.md) |
| Implementation evidence | [Stage 1](docs/STAGE_1_REPORT.md), [Stage 2](docs/STAGE_2_REPORT.md), [Stage 3](docs/STAGE_3_REPORT.md), [Stage 4](docs/STAGE_4_REPORT.md), [Stage 5](docs/STAGE_5_REPORT.md), [Stage 6](docs/STAGE_6_REPORT.md), [Stage 7](docs/STAGE_7_REPORT.md), [Stage 8](docs/STAGE_8_REPORT.md), [Stage 9](docs/STAGE_9_REPORT.md) |
| Foundation history | [Stage 0](docs/STAGE_0_REPORT.md), [Stage 0.1](docs/STAGE_0_1_REFINEMENT_REPORT.md) |

Key decisions: [architecture principles](docs/architecture/ADR/ADR-001-architecture-principles.md),
[execution semantics](docs/architecture/ADR/ADR-002-execution-domain-semantics.md),
[agent identity](docs/architecture/ADR/ADR-003-agent-definition-and-runtime-identity.md),
[Python selection](docs/architecture/ADR/ADR-004-implementation-language.md),
[single-agent protocol](docs/architecture/ADR/ADR-005-single-agent-runtime.md),
[Tool Runtime](docs/architecture/ADR/ADR-006-tool-runtime.md),
[Company Brain](docs/architecture/ADR/ADR-007-company-brain-and-knowledge-retrieval.md),
[governed Memory](docs/architecture/ADR/ADR-008-governed-memory.md),
[replaceable orchestration](docs/architecture/ADR/ADR-009-replaceable-orchestration-and-delegation.md), and
[governed communication](docs/architecture/ADR/ADR-010-multi-agent-communication-and-handoffs.md), and
[organizational structure](docs/architecture/ADR/ADR-011-departments-agent-registry-and-organizational-graph.md).

### Organization-aware work

The fictional Aurora Desk demo discovers Research, Product, and Marketing agents from
canonical capability IDs and explicit memberships. Each orchestration pins the exact
organization version. Registry discovery feeds the existing selector; all runtime grants
remain independently enforced. A department lead is an escalation destination and does
not inherit anyone else's permissions.

```mermaid
flowchart LR
    G[Organization Graph Version] --> D[Departments and Memberships]
    D --> R[Agent Registry]
    R --> S[AgentSelector]
    S --> A[Canonical Delegation]
    A --> E[AgentRun]
    P[Organization Policy] -. narrows routing .-> S
    P -. narrows messages and handoffs .-> E
```

See the [Stage 8 report](docs/STAGE_8_REPORT.md) for test evidence, exact bounds,
historical-version behavior, and the complete file inventory. Administration remains
trusted host code and storage remains in memory.

## Contributing

Keep changes focused on a demonstrated requirement or invariant. Start with the
relevant architecture decision and stage boundary, then include deterministic tests
and documentation for behavior changes. Material architecture changes need a new ADR;
do not silently rewrite accepted decisions.

Run the quality checks above before opening a pull request. Explain the change,
verification results, security implications, and remaining limitations so reviewers
can assess the evidence. Do not commit credentials or sensitive customer data.

Use [GitHub Issues](https://github.com/Amanux7/Nebula-OS-/issues) for reproducible bugs
and scoped proposals, and [Pull Requests](https://github.com/Amanux7/Nebula-OS-/pulls)
for code review. Avoid posting secrets or sensitive vulnerability details publicly.

## License

Released under the [MIT License](LICENSE). Copyright notice and terms are included
in the license file.
