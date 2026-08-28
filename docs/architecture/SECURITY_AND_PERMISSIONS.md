# Security and Permissions

## Security posture

Agent output, retrieved content, tool output, integration data, and model responses are untrusted inputs. Authority comes from authenticated identities and enforced policy, never from prompt text. Controls are deny-by-default, workspace-scoped, and applied immediately before privileged access or action.

## Initial permission model

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
