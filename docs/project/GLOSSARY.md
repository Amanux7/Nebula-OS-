# Glossary

## Stage 6 orchestration vocabulary

| Term | Definition | Boundary |
|---|---|---|
| Orchestration | Bounded application coordination that validates a plan, materializes canonical Tasks, delegates ready work, and checks completion. | Not Agent Runtime, planning intelligence, a queue, or an authority source. |
| OrchestrationStrategyPort | Replaceable asynchronous boundary that proposes a plan from a minimal typed request. | Its output is untrusted and cannot mutate domain state. |
| PlanProposal | Strategy-proposed ordered logical Tasks, dependencies, and requirements. | Not canonical state or an accepted plan. |
| PlanVersion | Immutable validated plan snapshot with monotonically increasing version and policy lineage. | Replanning appends history; it does not edit an accepted version. |
| PlannedTask | Logical task specification inside a PlanVersion. | Becomes a canonical Task only through materialization. |
| PlanMaterialization | Exact mapping of one PlanVersion's logical task IDs to canonical Tasks and an Execution. | Happens at most once per plan version. |
| OrchestrationRun | Bounded lifecycle coordinating one Goal under one strategy and policy. | Does not replace Goal, Execution, or AgentRun. |
| Agent requirements | Capabilities and exact tool/Knowledge/Memory/autonomy constraints required for a PlannedTask. | Requirements can narrow selection; they cannot grant authority. |
| AgentSelector | Deterministic policy component choosing an eligible exact published AgentDefinitionVersion. | Separate from planning and runtime execution. |
| Delegation | Assignment of one ready canonical Task to one exact AgentDefinitionVersion under a PlanVersion. | Not a message, permission grant, or TaskAttempt. |
| DelegationAttempt | Link from a Delegation to its exact Execution, TaskAttempt, and AgentRun. | Preserves retry/redelegation history. |
| TaskResultReference | Exact successful upstream Task/TaskAttempt/AgentRun result lineage made available to dependent work. | Referenced content is supplied data, not instructions, policy, or Knowledge. |
| ResultAggregator | Deterministic structural checker that confirms required Task results exist before Goal completion is requested. | Does not judge semantic output quality. |

This file is the canonical terminology reference. Documents should link here rather than invent local synonyms.

## Stage 5 precise memory vocabulary

| Term | Definition | Important distinction |
|---|---|---|
| MemoryCandidate | Bounded host-derived proposal for retained Episodic or Semantic Memory, bound to exact workspace, source run/references, authority, scope, sensitivity, and policy Version. | Not durable model output; policy rejection or human review occurs before an Entry exists. |
| MemoryEntry | Human-reviewed retained experience with immutable content/provenance and active, revoked, or superseded lifecycle. | Contextual experience, never authoritative Knowledge or completion evidence. |
| Episodic Memory | Reviewed retained observation or statement about a specific prior experience. | More concrete than Semantic Memory but still not automatically true or authoritative. |
| Semantic Memory | Reviewed retained generalized/structured information derived from experience. | Requires review in Stage 5; unsupported model inference is rejected. |
| MemoryScope | Exact workspace, agent, user, customer, task, or domain key attached to a candidate/entry. | Access is explicit; there is no implicit global scope. |
| MemoryAccessPolicy | Immutable exact scope and sensitivity grants on AgentDefinitionVersion. | A query narrows these grants and cannot expand them. |
| MemoryProvenance | Exact source AgentRun and bounded source references plus observed/stated/inferred/derived authority. | Reviewer identity is additionally preserved on the promoted Entry. |
| MemoryContextPack | Immutable workspace/run-bound snapshot of exact retrieved Entries, ranks, conflicts, query, strategy, and bounds. | Separate from EvidencePack; never passed to the grounding evaluator. |
| MemoryPolicy | Versioned deterministic candidate decision returning reject or requires-review in Stage 5. | Does not assess universal truth and has no auto-promote branch in this stage. |

Stage 5 uses `single-agent-memory-v1`, `governed-memory-v1`, and
`exact-subject-lexical-v1`. See [ADR-008](../architecture/ADR/ADR-008-governed-memory.md).

## Stage 4 precise knowledge vocabulary

| Term | Definition | Important distinction |
|---|---|---|
| KnowledgeSource | Stable workspace-scoped source identity, name, format, trust, and active/disabled state. | Current source mutation Version is separate from content Version. |
| KnowledgeSourceVersion | Immutable normalized content/hash, typed facts, metadata, timestamp, algorithms, and limits. | New publication appends a version; history never resolves through latest. |
| KnowledgeChunk | Immutable deterministic piece of an exact source version with ordinal, hash, and provenance. | Text projection, not learned information or an execution step. |
| KnowledgeScope | Immutable source ID and trust allowlists on AgentDefinitionVersion. | Query filters narrow but never expand grants. Collections are deferred. |
| KnowledgeQuery | Typed workspace/text/filter/limit request from trusted host code. | Query text is untrusted data, not executable policy. |
| EvidenceCandidate | A ranked chunk snapshot with exact provenance, declared trust, source-version timestamp, and score. | Relevance, trust, and freshness are independent. |
| EvidencePack | Immutable workspace/run-bound record of the exact bounded retrieval result and query/strategy. | Separate from active working state, supplied context, ToolReceipt, and Memory. |
| KnowledgeService | Application capability for publishing/disabling sources and retrieving/reading packs. | Not a ToolRuntime, planner, agent persona, or vector database. |

Stage 4 Company Brain implements governed source access and retrieval only. Working
State, Conversation History, Episodic/Semantic Memory, and authoritative Knowledge
remain distinct; no experience-derived Memory or automatic promotion is implemented.

## Shared product vocabulary

| Term | Definition | Important distinction |
|---|---|---|
| Agent | A reasoning actor configured to pursue a Goal or Task within explicit Context, capabilities, Working State, limits, and Policy. | Conceptual actor, not a prompt, Tool, Skill, Workflow, model, or Department. |
| AgentDefinition | Stable workspace-scoped logical identity and version lineage for an agent configuration. | Configuration identity, never active runtime participation. |
| AgentDefinitionVersion | Immutable behavior configuration for an AgentDefinition, including versioned instructions and capability/Policy/model references. | The exact version—not a mutable active alias—is bound to history. |
| AgentRun | Bounded runtime participation of exactly one AgentDefinitionVersion for a TaskAttempt within an Execution. | Standalone versioned Stage 2 record; replaces `AgentInstance`. Terminal runs do not reopen. |
| AgentInvocation | Typed command/request that asks the runtime to start an AgentRun. | A command, not the runtime participant or the enclosing Execution. |
| Skill | Reusable, versioned capability or procedure that describes how to perform a class of work and may compose Tools. | A Skill guides capability; a Tool executes an operation. |
| Tool | Executable, typed interface to a deterministic capability or external system, governed by Tool Permissions. | Does not decide why/when it should run and never grants itself authority. |
| ToolDefinition | Stable workspace-scoped Tool identity, name, description, and risk classification. | Not an invocation or mutable executable contract; Stage 3 clarifies the former Tool Definition umbrella. |
| ToolVersion | Exact immutable published ToolDefinition contract/configuration: named input/output schemas, executor kind, trust, timeout/byte bounds, and retry policy. | Historical receipts embed the exact snapshot, never a latest alias. |
| ToolGrant | Exact ToolId and Version granted by an immutable AgentDefinitionVersion. | Neither model text nor tool output can widen it; write classes remain denied. |
| ToolInvocation | One authorized attempt to execute an exact ToolVersion for an Action/AgentRun/TaskAttempt/Execution. | Running to succeeded, failed, or cancelled; a deliberate new Action is a new invocation even with identical arguments. |
| ToolReceipt | Immutable bounded runtime evidence of a terminal ToolInvocation, validated input/configuration/output or failure, timestamps, and provenance. | Proves what was observed, not objective truth; separate from model text and bounded Observation. |
| ToolRegistry | Registry resolving an exact published grant to an immutable version and executor, with workspace/enablement checks. | No dynamic function names or ambiguous latest-version selection. |
| ToolExecutor | Provider-neutral cooperative async port from validated input plus invocation context to untrusted result JSON. | Stage 3 has two read-only fixture adapters and a scripted fake; not a process sandbox. |
| ToolRuntimeService | Application responsibility for authorization, validation, invocation claims, execution, reconciliation, receipts, and bounded tool Observations. | Separate from AgentRuntimeService and from model reasoning. |
| Task | Bounded logical unit of work with inputs, acceptance criteria, dependencies, assignment, and lifecycle, belonging to exactly one Goal in the initial model. | Exists independently of its attempts and may have multiple TaskAttempts. |
| TaskAttempt | One concrete attempt to perform exactly one Task within exactly one Execution. | Retry creates a new attempt and preserves terminated history. |
| Goal | Desired outcome with constraints and acceptance criteria that may be decomposed into Tasks. | Outcome, not a plan, Task, attempt, or Execution; attempt failure does not automatically close it. |
| Workflow | Versioned defined sequence or graph of deterministic and/or agentic steps. | Need not contain or be supervised by an Agent. |
| Department | Organizational grouping for related AgentDefinitions, defaults, responsibility, discovery, and reporting. | Not an execution boundary by itself and not necessarily hierarchical. |
| Orchestrator | Component or future reasoning role that proposes or coordinates Tasks, routing, dependencies, progress, and recovery. | One replaceable strategy/role; it cannot bypass core domain validation and is not required on every path. |
| PlanningPort | Provisional interface seam through which deterministic, agentic, or hybrid planning strategies propose a Structured Plan. | Core domain logic does not depend on a particular implementation. |
| Structured Plan | Typed proposal describing Task decomposition, dependencies, routing, and constraints. | A proposal requiring software validation; it does not directly mutate state or grant authority. |
| Supervisor | Agent or component that monitors and directs subordinate work in a particular orchestration pattern. | One possible Orchestrator pattern, not a universal architecture requirement. |
| Handoff | Recorded transfer of Task responsibility and scoped context/artifact references from one actor to another. | Not free-form hidden agent chat. |
| Delegation | Assignment of a bounded Task and authority to an eligible actor while the delegator retains coordination/accountability semantics. | Cannot widen permissions. |
| Context | Bounded information assembled for one decision from Working State, authorized Knowledge, explicitly scoped future Memory, relevant Conversation History, prior Observations, and eligible capabilities. | Temporary input, not automatically persistent Knowledge or Memory. |
| Company Brain | Conceptual shared layer providing governed access to Knowledge, Memory, and relevant company state. | Not synonymous with RAG, embeddings, or one database. |
| Knowledge | Persistent internally or externally authoritative information available with provenance, access, and freshness semantics, such as company policies, product data, CRM records, and approved sources. | Distinct from agent-generated Memory and is not silently overridden by it. |
| Knowledge Source | Governed origin of Knowledge such as a document, website, note, or structured integration dataset. | Source content remains authoritative over derived indexes. |
| Memory | Governed retention derived from experience through explicit candidate, review, scope, lifecycle, and retrieval contracts. | Not Working State, Conversation History, authoritative Knowledge, or vector search. |
| Working State | Short-lived explicit runtime information required to continue the current Execution or TaskAttempt. | Deterministic current state, not long-term Memory. |
| Conversation History | Recorded interaction history where relevant to a use case. | Not automatically Context or long-term Memory. |
| Episodic Memory | Reviewed retained record about a prior statement, observation, event, or Execution experience. | Experience-derived and scoped; not authoritative Knowledge. |
| Semantic Memory | Reviewed retained generalized information derived from experience. | Stage 5 rejects unsupported model inference and requires human review. |
| MemoryEntry | One lifecycle-managed unit of Episodic or Semantic Memory promoted from an exact candidate. | Immutable content/provenance; revocation and supersession preserve history. |
| State | Explicit current domain/runtime condition required to continue, recover, or inspect work. | Canonical current state is not reconstructed solely from chat text, Events, or logs. |
| Action | Typed requested operation selected by deterministic logic, Workflow logic, or an Agent. | A request—not a result, StateTransition, Event, or proof of external effect. |
| Observation | Immutable typed information returned after an Action or external input, with provenance and trust classification. | Untrusted until validated; not automatically truth, instruction, or proof of success. |
| StateTransition | Append-only record of an accepted lifecycle change, stored alongside the subject's canonical current status. | Explicit transition history without requiring event sourcing. |
| Event | Append-only versioned record of a significant committed fact for audit, projection, or future integration. | Not a command, telemetry log, StateTransition, or automatic source of all application state. |
| Execution | One bounded root attempt to satisfy a Goal, run a Workflow, or handle another typed top-level invocation. | May coordinate multiple TaskAttempts; terminal retry creates a linked Execution. |
| Artifact | User-meaningful output such as a report, draft, or file linked to an Execution and stored by reference. | Not a verbose log payload. |
| Policy | Versioned machine-enforceable rule governing access, behavior, budgets, autonomy, or required approval. | Instructions cannot override Policy. |
| Permission | Effective authority for a principal/resource/action under Policy and current context. | Eligibility is not permission; grants can only be narrowed downstream. |
| Approval | Recorded human decision about an exact proposed action, including its material payload, scope, policy context, and validity. | General trust or previous approval does not authorize a changed action. |
| Approval Request | Pending lifecycle object that binds an exact proposed Action to eligible approvers, risk, expiry, and payload digest. | An approved request is single-use and revalidated. |
| Evaluation | Versioned assessment of behavior or output against explicit criteria, fixtures, references, or rubrics. | Not the same as a deterministic software test. |
| Autonomy | Degree to which execution may proceed without human action, always bounded by Policy, permissions, resources, budgets, and escalation rules. | A maximum ceiling, not a guarantee the Agent acts. |
| Connection | Workspace-scoped reference to an external system authorization and its granted scopes; secrets live behind a protected reference. | Not a Tool or blanket permission to every operation. |
| Structured Decision | Schema-validated runtime output selecting an allowed action and carrying arguments, evidence references, and non-sensitive reason metadata. | Does not include or require hidden chain-of-thought. |
| Execution Trace | Query/view that correlates TaskAttempts, AgentRuns, Actions, Observations, StateTransitions, Events, approvals, usage, errors, and outcomes. | A projection, not a generic ExecutionStep store, canonical state, or chain-of-thought transcript. |
| Reason Category | Stable non-sensitive classification explaining why an action/state was selected (for example `insufficient_evidence` or `policy_requires_approval`). | Not verbatim private reasoning. |
| AgentWorkingState | Bounded iteration metadata, recent Observations, missing fields, and pending-invocation guard for one AgentRun. | Short-lived run state, not Memory; limits survive wait/resume. |
| ModelPort | Provider-neutral cooperative asynchronous model invocation boundary. | Stage 2 supplies only a scripted fake adapter, not a live AI model. |
| ResearchBrief | Structured accepted findings, gaps, source references, and software-rendered summary from supplied facts or approved receipt evidence. | Stage 3 extends exact fixture matching to successful same-run receipts, not general natural-language entailment. |

## Autonomy levels

- **Level 0 — Observe:** watch and report.
- **Level 1 — Recommend:** suggest an action; the user acts.
- **Level 2 — Draft:** prepare an action; human approval is required to execute.
- **Level 3 — Bounded Execution:** execute automatically inside explicit rules, limits, and escalation boundaries.
- **Level 4 — Autonomous:** independently pursue goals within stringent Policy and kill controls.
