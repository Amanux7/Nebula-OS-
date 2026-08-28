# Product Requirements Document

## 1. Product name

**Agent Company OS** — working title.

## 2. Executive summary

Agent Company OS is a platform for defining and operating an AI-native organization. A user will be able to express a goal, delegate bounded work to specialized agents and deterministic workflows, grant narrowly scoped tools, supply shared company knowledge, approve consequential actions, and inspect evidence of what occurred. The product is an operating layer for coordinated work—not a gallery of independent chatbots.

Stage 0 establishes product and engineering contracts only. It does not implement AI behavior.

## 3. Problem statement

Teams using AI today commonly accumulate disconnected prompts and assistants. These systems lack a durable organization model, share context poorly, blur delegation and ownership, and often treat chat history as memory. Tool access is frequently over-broad, external actions are hard to verify, and human oversight is bolted on after execution. Hidden state and weak traces make failures difficult to reproduce. Agent definitions, skills, integrations, and workflows are rarely reusable across use cases.

The result is automation that demos well but cannot be trusted with meaningful business work. Users need a system in which responsibilities, state, permissions, evidence, approvals, failures, and costs are explicit.

## 4. Product vision

The long-term product is an operating system for an AI-powered company: users define company context and outcomes; the system determines whether deterministic automation or reasoning is appropriate; capable agents collaborate through bounded tasks and handoffs; and every consequential action is policy-checked, observable, and evaluable. Organizational structures remain configurable rather than hard-coded.

## 5. Product principles

1. Trustworthy before autonomous.
2. Observable before invisible.
3. Explicit state over hidden behavior.
4. Compose agents from reusable skills and governed tools.
5. Humans remain in control and can intervene.
6. Use deterministic systems where possible; use agents where reasoning adds value.
7. Use typed, structured outputs at system boundaries.
8. Prefer cited evidence over unsupported assumptions.
9. Fail safely, visibly, and recoverably.
10. Grant least-privilege tool access.
11. Make actions and state transitions auditable.
12. Avoid dependence on one model provider where practical.

## 6. Target users

The initial candidate users are solo founders, small startup teams, operations leaders, automation builders, agencies, and SMB owners. Stage 0 does not declare a final beachhead; [Personas](PERSONAS.md) describes the working hypotheses that must be validated.

## 7. Jobs to be done

- When work spans multiple specialties, help me delegate it without manually coordinating every prompt.
- When an AI proposes or performs work, show me the basis, state, tools, approvals, and outcome so I can trust or correct it.
- When a recurring process is sufficiently understood, let me encode repeatable workflow while reserving reasoning for ambiguous steps.
- When company context changes, give authorized workers consistent, source-aware access without copying information into every prompt.
- When an external action is risky, enforce policy and obtain approval before execution.
- When execution fails, preserve enough evidence to diagnose, retry safely, or take over.

## 8. Primary use cases

Candidate use cases include company research, lead intelligence, content planning, knowledge management, inbox assistance, support triage, operational monitoring, reporting, and governed workflow execution. The MVP will validate a narrow, read-heavy knowledge-work flow before expanding to high-impact write actions.

## 9. Core product objects

| Object | Product meaning |
|---|---|
| Agent | Reasoning actor configured to pursue goals within policy. |
| Department | Organizational grouping and policy/visibility boundary for related agents. |
| Skill | Reusable capability or procedure; it may guide reasoning or compose tools. |
| Tool | Executable, typed interface to a deterministic capability or external system. |
| Task | Bounded logical unit of work with acceptance criteria and lifecycle. |
| Goal | Desired outcome that may be decomposed into tasks. |
| Workflow | Versioned sequence or graph of deterministic and agentic steps. |
| Knowledge Source | Governed source whose content can be retrieved with provenance. |
| Memory | Retained information derived from experience and governed by scope and retention. |
| Execution | One bounded root attempt to satisfy a Goal, run a Workflow, or handle another typed top-level invocation. |
| Policy | Machine-enforceable rule governing access or behavior. |
| Approval | Recorded human decision authorizing, rejecting, or requesting changes to a proposed action. |
| Evaluation | Recorded assessment of output or behavior against defined criteria. |

Canonical definitions and lifecycles are in [Domain Model](../architecture/DOMAIN_MODEL.md) and [Glossary](../project/GLOSSARY.md). Internally, TaskAttempt preserves retry history, while Action, Observation, StateTransition, and Event remain distinct runtime records rather than a generic ExecutionStep.

## 10. Company Brain

The Company Brain is the conceptual shared intelligence layer through which authorized agents access company knowledge, memory, and relevant current state. Inputs may include documents, PDFs, Markdown, notes, websites, structured business data, integrations, and later transcripts. It must preserve provenance, access controls, freshness, and source boundaries.

It is not synonymous with a vector database or RAG. Retrieval, structured queries, search, curated facts, temporal state, and artifact access may all contribute. Knowledge and memory remain operationally distinct; see [Data Architecture](../architecture/DATA_ARCHITECTURE.md).

## 11. Agent system

An AgentDefinition is stable configuration identity; an immutable AgentDefinitionVersion specifies role, instructions, capabilities, eligible Tools and Knowledge, default Policies, model policy, and evaluation profile. A future AgentInvocation requests a bounded AgentRun for a TaskAttempt. Historical behavior binds the exact AgentDefinitionVersion so later changes do not reinterpret prior Executions. The future runtime assembles authorized Context, invokes a replaceable model through a typed boundary, validates a structured decision, creates an allowed Action, records Observations and StateTransitions, evaluates progress, and terminates, continues, or escalates within limits.

Agents never receive unrestricted credentials. Their effective authority is the intersection of workspace, user, agent, task, tool, connection, and autonomy policies. No hidden chain-of-thought is required or stored.

## 12. Agent organization

Workspaces may group agents into departments for discoverability, responsibility, policy defaults, and reporting. Hierarchy is a configurable view over real definitions and relationships, not a fixed org chart. An agent may collaborate across departments when authorized. Agent count follows demonstrated need; the product should favor a small set of capable agents over shallow role wrappers.

## 13. Chief of Staff and orchestration

A future top-level orchestrator may interpret goals, choose a deterministic workflow or agentic plan, decompose work, select eligible agents, monitor dependencies, recover from failures, and synthesize results. It is not required to mediate every workflow: direct agent invocation and deterministic workflows must remain possible. Whether the orchestrator is itself modeled as an Agent remains an open question.

## 14. Human in the loop

Users must be able to review recommendations, inspect and edit drafts, approve or reject proposed actions, add constraints, respond to escalations, cancel work, retry safe steps, and take over manually. Approval records bind the reviewed action payload and policy context so a materially changed action requires new approval.

## 15. Autonomy

| Level | Meaning | Allowed behavior |
|---|---|---|
| 0 — Observe | Watch and report | Read and summarize permitted state; no proposed external change. |
| 1 — Recommend | Suggest | Produce recommendations; user acts. |
| 2 — Draft | Prepare | Create an action payload or artifact; approval required to execute. |
| 3 — Bounded Execution | Execute within rules | Act within explicit scopes, budgets, rate limits, and escalation boundaries. |
| 4 — Autonomous | Operate independently | Pursue goals within stringent policy, monitoring, budgets, and kill controls. |

Autonomy is an execution constraint, not an agent personality setting. MVP supports Levels 0–2 and a deliberately narrow subset of Level 3 only if safety validation succeeds.

## 16. Agent execution visibility

Users should be able to inspect which definition/version ran, trigger and assigned task, relevant source references, structured decisions and reason categories, tools requested and results, state transitions, duration, retries, failures, approvals, handoffs, costs, and evaluations. The system exposes decision metadata and evidence, not hidden chain-of-thought.

## 17. Agent graph and organization visualization

A future graph may visualize definitions, departments, dependencies, active executions, task handoffs, and health. It is a projection of canonical stored state and traces; edits must flow through validated application contracts. The graph is never the source of truth.

## 18. Analytics

Future analytics may include execution volume, success and escalation rates, completion time, agent/tool usage, error and retry rates, approval outcomes, model/token cost, and evaluation scores. Metrics must be sliceable by version and use case and must not reward raw activity over successful, safe outcomes.

## 19. MVP

The recommended MVP is one workspace with one manager/orchestrator and three specialized agents: Research, Analyst, and Writer/Reporter. It includes a small read-first tool registry, basic shared knowledge with provenance, bounded execution, structured traces, artifact outputs, and approval before any external write. A representative workflow is: research a company or topic, analyze evidence, and produce an approval-ready brief.

Detailed boundaries are in [MVP Scope](MVP_SCOPE.md).

## 20. Non-goals

The initial product will not provide dozens of placeholder agents, unrestricted autonomous operation, a general-purpose browser/computer operator, a marketplace, broad SaaS coverage, agent-generated production code execution, self-modifying prompts or policies, voice operation, graph-first editing, enterprise billing, or a claim of fully autonomous company operation.

## 21. Functional requirements

| ID | Requirement |
|---|---|
| FR-001 | A user can create a workspace with an isolated identity and configuration. |
| FR-002 | A user can define, version, enable, disable, and inspect an AgentDefinition and its AgentDefinitionVersions. |
| FR-003 | The system can register versioned Skills separately from Agents and Tools. |
| FR-004 | The system can register typed Tool Definitions with declared permissions and risk metadata. |
| FR-005 | A user can add, remove, scope, and inspect Knowledge Sources with provenance. |
| FR-006 | A user can create a Goal with constraints and acceptance criteria. |
| FR-007 | The system can decompose an eligible Goal into bounded Tasks and expose the proposed plan. |
| FR-008 | The system can invoke an eligible Agent for a Task using an immutable configuration version. |
| FR-009 | The runtime can enforce iteration, time, token/cost, and tool-call limits. |
| FR-010 | Model decisions and tool requests cross validated structured boundaries. |
| FR-011 | Every Goal, Task, TaskAttempt, and Execution follows an explicit lifecycle; Actions, Observations, StateTransitions, and Events use separate typed records. |
| FR-012 | Policy is checked before privileged context access and tool execution. |
| FR-013 | The system can create an Approval Request containing the exact proposed action. |
| FR-014 | A user can approve, reject, edit-and-resubmit, cancel, or take over eligible work. |
| FR-015 | Tool execution is idempotent where possible and records verifiable results. |
| FR-016 | Users can inspect execution traces, source references, failures, retries, approvals, and evaluations. |
| FR-017 | Users can cancel active Executions and retry from a defined safe boundary using a new linked Execution or TaskAttempt rather than rewriting terminal history. |
| FR-018 | Artifacts are stored separately from trace metadata and linked to executions. |
| FR-019 | The system supports deterministic workflows without requiring an agent supervisor. |
| FR-020 | Authorization and workspace isolation apply to every product object and read/write path. |
| FR-021 | Users can configure autonomy no higher than policy permits. |
| FR-022 | The system records auditable configuration and permission changes. |
| FR-023 | Evaluations can be attached to outputs and execution versions. |
| FR-024 | External action success is reported only when supported by a tool receipt or equivalent evidence. |

## 22. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-001 | **Reliability:** executions use explicit state machines and never silently disappear. |
| NFR-002 | **Security:** deny by default, isolate workspaces, encrypt secrets, and audit privileged actions. |
| NFR-003 | **Observability:** correlate logs, metrics, traces, and evaluation records by execution identifier. |
| NFR-004 | **Extensibility:** add providers, agents, skills, and tools through versioned contracts. |
| NFR-005 | **Latency:** define per-use-case service objectives and surface long-running progress rather than hiding waits. |
| NFR-006 | **Recovery:** retries, resumption, and cancellation preserve idempotency and terminal-state correctness. |
| NFR-007 | **Maintainability:** business rules live in testable code/configuration rather than only in prompts. |
| NFR-008 | **Testability:** regular suites run with deterministic model and tool doubles and no paid API dependency. |
| NFR-009 | **Portability:** provider-specific behavior remains behind adapters where requirements allow. |
| NFR-010 | **Privacy:** collect and retain only required content; support deletion and documented retention. |
| NFR-011 | **Scalability:** execution workers can scale independently from request handling without changing contracts. |
| NFR-012 | **Accessibility:** core approval and trace experiences target WCAG 2.2 AA when UI work begins. |

Numeric targets are deliberately assigned per validated MVP workflow in Stage 1/2 rather than invented before prototypes exist.

## 23. Risks

Primary product risks are insufficient trust, unclear initial customer, automation that requires more supervision than it saves, and premature breadth. Technical risks include hallucination, prompt injection, tool misuse, cross-workspace leakage, duplicate effects, runaway loops/cost, stale context, hidden failures, and provider outages. Controls and ownership are tracked in the [Risk Register](../engineering/RISK_REGISTER.md).

## 24. Future vision

After validating the runtime, the product can add durable workflow orchestration, richer Company Brain capabilities, scoped memory, multi-agent delegation, department registries, policy-driven bounded autonomy, execution graph views, evaluations, and carefully selected integrations. Each expansion must retain explicit state, least privilege, human intervention, evidence, and versioned behavior.
