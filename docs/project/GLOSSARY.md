# Glossary

This file is the canonical terminology reference. Documents should link here rather than invent local synonyms.

| Term | Definition | Important distinction |
|---|---|---|
| Agent | A reasoning actor configured to pursue a Goal or Task within explicit context, tools, state, limits, and Policy. | Not a prompt, Tool, Skill, Workflow, model, or department. |
| Agent Definition | Immutable versioned configuration describing an Agent's role, instructions, eligible capabilities, knowledge scopes, limits, autonomy ceiling, and evaluation profile. | Configuration, not a running process. |
| Agent Instance | Runtime identity created from one Agent Definition version for an invocation/session boundary within an Execution. | Transient runtime actor, not reusable definition. |
| Skill | Reusable, versioned capability or procedure that describes how to perform a class of work and may compose Tools. | A Skill guides capability; a Tool executes an operation. |
| Tool | Executable, typed interface to a deterministic capability or external system, governed by Tool Permissions. | Does not decide why/when it should run and never grants itself authority. |
| Tool Definition | Versioned contract for a Tool operation, including schemas, risk/side-effect class, timeout/retry semantics, and required connection/scopes. | Definition, not a particular call. |
| Task | Bounded unit of work with inputs, owner/assignee, acceptance criteria, dependencies, and lifecycle. | More concrete than a Goal; may have multiple Execution attempts. |
| Goal | Desired outcome with constraints and acceptance criteria that may be decomposed into Tasks. | Outcome, not the plan or execution. |
| Workflow | Versioned defined sequence or graph of deterministic and/or agentic steps. | Need not contain or be supervised by an Agent. |
| Department | Organizational grouping for related Agent Definitions, defaults, responsibility, discovery, and reporting. | Not an execution boundary by itself and not necessarily hierarchical. |
| Orchestrator | Component or future reasoning role that turns Goals into bounded Tasks and coordinates routing, dependencies, progress, and recovery. | Not required on every execution path. |
| Supervisor | Agent or component that monitors and directs subordinate work in a particular orchestration pattern. | One possible Orchestrator pattern, not a universal architecture requirement. |
| Handoff | Recorded transfer of Task responsibility and scoped context/artifact references from one actor to another. | Not free-form hidden agent chat. |
| Delegation | Assignment of a bounded Task and authority to an eligible actor while the delegator retains coordination/accountability semantics. | Cannot widen permissions. |
| Context | Bounded information assembled for one decision: task state, relevant Knowledge, scoped Memory, prior Observations, and eligible capability descriptions. | Temporary model input, not automatically persistent Knowledge or Memory. |
| Company Brain | Conceptual shared layer providing governed access to Knowledge, Memory, and relevant company state. | Not synonymous with RAG, embeddings, or one database. |
| Knowledge | Persistent externally grounded information available with provenance, access, and freshness semantics. | Distinct from experience-derived Memory. |
| Knowledge Source | Governed origin of Knowledge such as a document, website, note, or structured integration dataset. | Source content remains authoritative over derived indexes. |
| Memory | Governed retained information derived from prior experience/interactions, with scope, provenance, confidence, and retention. | Not execution scratch state, chat history, Knowledge, or vector search. |
| Memory Entry | One persisted, lifecycle-managed unit of Memory. | Candidate memories require promotion/validation policy. |
| State | Explicit current domain/runtime condition required to continue, recover, or inspect work. | Canonical state is not reconstructed solely from chat text or logs. |
| Observation | Immutable, typed, sanitized fact returned by a model, Tool, retrieval, Policy, or system operation to the runtime. | It is untrusted input until validated; not necessarily truth or instruction. |
| Execution | One concrete attempt to complete a Goal, Task, Workflow, Agent invocation, or operation. | Retrying creates/identifies a distinct attempt rather than erasing history. |
| Execution Step | Atomic recorded action attempt or state transition within an Execution. | Provides retry/idempotency and trace granularity. |
| Artifact | User-meaningful output such as a report, draft, or file linked to an Execution and stored by reference. | Not a verbose log payload. |
| Policy | Versioned machine-enforceable rule governing access, behavior, budgets, autonomy, or required approval. | Instructions cannot override Policy. |
| Permission | Effective authority for a principal/resource/action under Policy and current context. | Eligibility is not permission; grants can only be narrowed downstream. |
| Approval | Recorded human decision about an exact proposed action, including its material payload, scope, policy context, and validity. | General trust or previous approval does not authorize a changed action. |
| Approval Request | Pending lifecycle object that binds a proposed action to eligible approvers, risk, expiry, and payload digest. | An approved request is single-use and revalidated. |
| Evaluation | Versioned assessment of behavior or output against explicit criteria, fixtures, references, or rubrics. | Not the same as a deterministic software test. |
| Autonomy | Degree to which execution may proceed without human action, always bounded by Policy, permissions, resources, budgets, and escalation rules. | A maximum ceiling, not a guarantee the Agent acts. |
| Connection | Workspace-scoped reference to an external system authorization and its granted scopes; secrets live behind a protected reference. | Not a Tool or blanket permission to every operation. |
| Structured Decision | Schema-validated runtime output selecting an allowed action and carrying arguments, evidence references, and non-sensitive reason metadata. | Does not include or require hidden chain-of-thought. |
| Execution Trace | Correlated structured record of versions, actions, observations, transitions, approvals, usage, errors, and outcomes. | Not canonical state by itself and not a chain-of-thought transcript. |
| Reason Category | Stable non-sensitive classification explaining why an action/state was selected (for example `insufficient_evidence` or `policy_requires_approval`). | Not verbatim private reasoning. |

## Autonomy levels

- **Level 0 — Observe:** watch and report.
- **Level 1 — Recommend:** suggest an action; the user acts.
- **Level 2 — Draft:** prepare an action; human approval is required to execute.
- **Level 3 — Bounded Execution:** execute automatically inside explicit rules, limits, and escalation boundaries.
- **Level 4 — Autonomous:** independently pursue goals within stringent Policy and kill controls.
