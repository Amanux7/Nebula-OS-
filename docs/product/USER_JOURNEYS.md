# User Journeys

Each journey identifies the user-visible flow and the important system interactions. Exact UI is intentionally unspecified.

## Journey A — Create a company workspace

1. User names the workspace and accepts initial data/retention defaults.
2. Application creates an isolated Workspace and owner membership.
3. Policy service assigns deny-by-default permissions and an audit event.
4. System presents the empty state and safe next steps.

**Success:** all later objects are workspace-scoped; no agents or integrations are silently provisioned.

## Journey B — Add company knowledge

1. User chooses a supported source and sees requested access scope.
2. System validates type, size, authorization, and malware/content safety controls.
3. Ingestion records the original source, provenance, access policy, status, and freshness metadata.
4. Processing creates searchable representations without replacing the source of record.
5. User can preview, restrict, refresh, or remove the source.

**Success:** an authorized retrieval returns source references; a denied actor cannot discover or retrieve the source.

## Journey C — Configure an agent

1. User selects a role template or starts from a minimal definition.
2. User sets purpose, instructions, eligible skills, knowledge scopes, tools, limits, autonomy, and evaluation profile.
3. System validates conflicts and calculates effective permissions.
4. User saves an immutable version and optionally activates it.
5. A sandboxed fixture can test behavior before production use.

**Success:** future invocations identify the exact version and cannot exceed effective policy.

## Journey D — Assign a goal

1. User states an outcome, constraints, acceptance criteria, deadline, and optional budget.
2. Application records the Goal and chooses or proposes a workflow/manager.
3. Orchestration produces bounded Tasks, dependencies, owners, and expected approvals.
4. User reviews the plan when policy requires it.
5. Execution begins and progress remains visible.

**Success:** the goal reaches a defined terminal state with artifacts and evidence, or visibly escalates/fails.

## Journey E — Observe execution

1. User opens an active or historical Execution.
2. UI shows current state, agent/version, task, elapsed time, limits, and step timeline.
3. Each step exposes source references, action category, tool status, state transition, and artifacts.
4. User may cancel, approve, or take over if authorized.

**Success:** the user understands what happened without access to hidden chain-of-thought.

## Journey F — Approve an action

1. Runtime pauses before a policy-controlled external action.
2. Approval Request shows exact action, destination, material arguments, evidence, expected effects, risk, and expiry.
3. User approves, rejects with reason, or edits and resubmits.
4. Policy revalidates actor, payload hash, freshness, and limits.
5. Tool runtime executes once and records a receipt; changed payloads require a new approval.

**Success:** execution cannot bypass approval, and approval is bound to what was executed.

## Journey G — Inspect why something failed

1. User sees a failed or escalated terminal state and a concise error category.
2. Trace shows the failing step, sanitized inputs, attempts, tool/provider responses, and state transitions.
3. System distinguishes retryable, user-correctable, policy-denied, and permanent failures.
4. User retries from a safe checkpoint, changes configuration as a new version, or takes over.

**Success:** no duplicate side effect occurs, and the resolution is auditable.

## Journey H — Add a tool or integration

1. User selects a Tool Definition or creates one through an administrative flow.
2. System displays capabilities, argument schema, risk class, scopes, and approval defaults.
3. User authorizes a Connection; secrets enter the secret store and are never exposed to the agent.
4. A health/permission check runs through the tool boundary.
5. User grants selected agents or workflows narrower Tool Permissions.

**Success:** only permitted actions are callable; revocation takes effect promptly and is logged.

## Cross-journey system rules

- Configuration and policy changes are versioned and audited.
- Long-running work is asynchronous, cancellable, and stateful.
- Every external success claim requires evidence.
- User-facing explanations rely on structured reason categories and references, never hidden chain-of-thought.
