# Security and Permissions

## Stage 5 memory controls

- Memory has no model-controlled write Action. Trusted host code derives candidates
  from canonical, successful source-run records.
- Every eligible candidate requires named human review; semantic memory is never
  automatically promoted. Unsupported model inference, Knowledge duplication, and
  detectable credential patterns are rejected.
- Exact scope and sensitivity grants are pinned to AgentDefinitionVersion. Query
  filters only narrow grants, and there is no implicit workspace-global access.
- Restricted and sensitive entries require corresponding grants. Cross-workspace
  create, review, revoke, supersede, retrieve, and historical-read paths are denied.
- Revocation, supersession, expiry, and grant changes are checked again after model
  invocation so stale context cannot commit a decision.
- Memory remains untrusted contextual data and cannot ground a completion or override
  authoritative Knowledge. Conflicts are retained and visibly flagged.

The regex secret check is only defense in depth. Authentication, DLP, encryption,
production deletion/redaction, reviewer authorization, and durable policy
linearization remain required before real sensitive data is permitted.

## Security posture

### Implemented Stage 4 controls

KnowledgeScope pins source identities and trust classes on AgentDefinitionVersion.
Query filters only narrow grants. Eligibility precedes ranking; candidate/store checks
reject forged, foreign, altered, ungranted, disabled, or incorrectly versioned evidence.
Source/chunk reads check workspace; pack reads additionally check run identity.
Active evidence is rechecked before and after model invocation, including disablement
during I/O. Source updates preserve exact historical evidence rather than replacing it.

Text/Markdown/JSON are bounded data, not executable formats. UTF-8, controls, JSON
shape/duplicate keys, lengths, chunk counts, query filters, full pack size, and per-run
retrieval count are enforced. Caller and tool source IDs cannot spoof knowledge:
provenance. Exact structured facts, not free-text paraphrases, may ground completion.
Source/query injection fixtures prove unchanged software authority and no unauthorized
source content in results—not perfect model resistance to adversarial text.

Trusted host code initiates publication and retrieval; there is no authenticated API
or automatic secret classifier. Operators must not publish secret-bearing source data
to an agent's allowed scope. Events contain allowlisted correlation/size/version fields,
not raw query or document bodies. Historical packs contain query/evidence and need
future retention/redaction policy. In-process adapter trust and offline corpus bounds
are not a hostile-code sandbox. See [ADR-007](ADR/ADR-007-company-brain-and-knowledge-retrieval.md).

Agent output, retrieved content, tool output, integration data, and model responses are untrusted inputs. Authority comes from authenticated identities and enforced policy, never from prompt text. Controls are deny-by-default, workspace-scoped, and applied immediately before privileged access or action.

## Initial permission model

The broader controls below are the target security design, not all implemented
capabilities. Stage 3 implements the narrow tool boundary in
[ADR-006](ADR/ADR-006-tool-runtime.md): exact immutable AgentDefinitionVersion grants,
workspace-scoped tool registry, action allowlist, read-only risk enforcement,
schema/byte/time/call limits, and post-I/O version/enablement checks.
No authenticated API, secret broker, connection/OAuth system, human approval engine,
transport sandbox, or production telemetry redaction service exists yet.

Stage 3 ToolRisk uses `read_only`, `internal_write`, `external_write`, and `high_risk`;
only `read_only` executes. This is a coarse initial classification, not an alternative
implementation of the future R0–R4 matrix. Granting a write class still cannot run it.
Registry disablement invalidates in-flight results through revision checks; it is
not a guarantee an upstream process has stopped or a distributed revocation protocol.

Tool-result text is labelled untrusted data, even from trusted fixture configuration.
An adversarial notes fixture requests database deletion; software rejects the proposed
unregistered tool without changing grants. Successful receipts are scoped to the run,
and reserved source prefixes prevent caller/tool data impersonating receipt evidence.
Raw malformed/oversized outputs and executor exception messages are not stored.
Future credentials must stay in protected executor configuration, never in tool
descriptors or model context. No credential fields or secrets are needed in Stage 3.

An authorization request is evaluated over:

```text
principal + workspace + resource + action + purpose/task
+ AgentDefinitionVersion + tool/operation + connection
+ autonomy level + data classification + limits + current state
```

The result is one of `ALLOW`, `DENY`, or `REQUIRE_APPROVAL`, with a rule/version and reason code. Effective permission is the intersection of user/service authority, workspace policy, agent limits, task scope, Tool Permission, Connection scopes, and runtime budgets. No layer can widen its parent's grant.

### Roles and grants

- Workspace roles provide coarse administrative and operating rights.
- Resource grants scope access to departments, sources, agents, workflows, artifacts, and executions.
- Tool Permissions grant named operations and resource scopes, not whole connectors by default.
- Conditions constrain time, destination, amount/volume, data classification, rate, budget, and autonomy.
- Explicit deny and expired/revoked grants take precedence.

### Tool risk classes

| Class | Example effect | Default control |
|---|---|---|
| R0 | Pure local transformation of authorized data | Allow within execution limits. |
| R1 | External or internal read | Allow only scoped resources; audit access. |
| R2 | Reversible/draft write | Level 2 approval by default; Level 3 only with narrow policy. |
| R3 | Consequential external write, send, publish, or financial/change action | Explicit approval, strong validation, idempotency, receipt; no broad MVP autonomy. |
| R4 | Destructive, irreversible, privilege/security, or high-impact action | Deny by default; exceptional multi-party or out-of-band controls if ever supported. |

Risk classification is operation-specific. A connector may contain both reads and destructive writes.

## Human approval

An Approval Request contains the exact normalized action, material arguments and destination, expected effect, evidence, risk class, policy basis, eligible approvers, expiry, and payload digest. Approval is single-use and revalidated immediately before execution. Editing, stale state, scope change, expired credentials, changed payload, or changed policy invalidates prior approval.

## Secrets and connections

- Secrets reside in a dedicated secret manager or equivalent encrypted boundary.
- Agent/model context receives capability metadata, never raw credentials.
- Tool adapters receive short-lived or narrowly scoped secret access at execution time.
- OAuth scopes are minimized; connection health, expiry, revocation, and rotation are tracked.
- Secrets are redacted at structured logging boundaries and tested with canary patterns.

## Workspace and sensitive-data isolation

- Workspace identity is mandatory in records, storage paths, jobs, cache keys, and telemetry context.
- Authorization occurs on reads as well as writes, including retrieval and artifact download.
- Data classification controls model/provider routing, retention, export, logging, and integration use.
- Bulk export, deletion, support access, and administrative impersonation need dedicated audited flows.
- Production data is not used in tests/evaluations without an approved de-identification process.

## Prompt injection and untrusted content

1. Treat retrieved documents, websites, emails, and tool output as data, not system instructions.
2. Separate trusted instructions and policy from quoted untrusted content in the context contract.
3. Minimize exposed tool descriptions and permissions for each task.
4. Validate all model-proposed operations outside the model.
5. Require provenance and flag content that attempts to redirect authority or request secrets.
6. Apply output/content safety checks appropriate to the use case; do not claim perfect prompt-injection detection.
7. Use approval and isolation to limit blast radius when detection fails.

## Tool execution controls

- Typed allowlisted operation and argument schemas.
- Destination/resource constraints and server-side semantic validation.
- Rate, concurrency, cost, and volume limits.
- Network egress allowlists or brokered access where appropriate.
- Sandboxing for any future code/file execution; unrestricted environment access is prohibited.
- Idempotency keys, outcome receipts, and reconciliation for ambiguous failures.
- Timeouts, response size limits, trust classification, and sanitization of tool output.

## Audit and observability

Audit authentication changes, membership/role changes, definition/policy versions, permission grants/revocations, knowledge access where required, approvals, tool attempts/results, secret access metadata, and administrative actions. Audit records must be tamper-evident enough for the risk level, access-controlled, retained separately from verbose debug logs, and correlated by execution ID. Do not record credentials, hidden chain-of-thought, or unnecessary private data.

## Autonomous execution boundaries

- Level is capped by policy and risk class, with explicit goals, resources, deadlines, budgets, iteration/tool limits, and escalation rules.
- Kill/cancel controls and policy revocation must take effect promptly.
- A history of success may inform a policy change but never automatically grants new authority.
- High-impact actions remain approval-gated until a documented risk assessment and production evidence justify otherwise.

## Threat-focused verification

Required security tests include cross-workspace access, confused-deputy attempts, indirect prompt injection, tool argument smuggling, approval replay/tampering, revoked connection use, duplicate side effects, secret leakage in logs/model context, malicious large tool output, rate-limit bypass, and cancellation races.

## Initial incident response expectations

Operators must be able to revoke a Connection or Tool Permission, disable an Agent/Workflow version, cancel active work, quarantine a Knowledge Source, identify affected executions, preserve sanitized evidence, and notify affected users according to an incident plan. Detailed production procedures belong to a later operational runbook.
