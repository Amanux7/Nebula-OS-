# Observability Strategy

## Objectives

Observability must let users and operators answer: what ran, under which version and authority, what state changed, which dependencies were used, what failed, what it cost, and whether the outcome was acceptable. It supports diagnosis and audit but does not replace canonical execution state.

## Correlation model

Every signal carries `workspace_id` in protected context and, when applicable:

```text
execution_id, root_execution_id, parent_execution_id
agent_id, agent_definition_version
goal_id, task_id, workflow_id, workflow_version
execution_step_id, attempt
tool_id, tool_version, tool_call_id
approval_request_id, evaluation_id
```

User-facing views may hide internal identifiers, but cross-workspace querying is prohibited unless separately authorized.

## Signals

### Traces

Spans cover API acceptance, orchestration, context assembly, model invocation, policy decision, approval wait/resume, tool execution, persistence, and evaluation. Long approval waits are represented as linked phases/events rather than an open span held indefinitely.

### Metrics

- execution count and terminal state by type/version;
- duration and queue/wait/active time distributions;
- model/provider latency, error, token usage, and estimated cost;
- tool calls, result status, retry and outcome-unknown rate;
- errors by stable category and retryability;
- handoffs, loop/stall detection, and escalation rate;
- approval requested/approved/rejected/expired and wait time;
- evaluation scores, regressions, and evaluator errors;
- budget/limit utilization, cancellations, worker lease loss, queue lag, and source freshness.

Metrics use bounded-cardinality labels. IDs, prompts, URLs, user text, and arbitrary error strings do not become metric labels.

### Structured logs

Logs use event names, severity, stable error codes, correlation IDs, component/version, state before/after, duration, retry metadata, and sanitized references. Large model/tool payloads are stored only when policy permits, separately access-controlled, and referenced by ID.

### Audit events

Security-relevant immutable events include membership/role changes, policy/definition versions, permission/connection changes, approval decisions, privileged reads, tool attempts/results, and administrative intervention. Audit access and retention exceed ordinary debug-log controls where required.

## What must not be logged

- secrets, credentials, authorization headers, signed URLs, or encryption material;
- hidden chain-of-thought or private model reasoning;
- full prompt/context/tool payloads by default;
- unnecessary personal or customer data;
- raw sensitive documents, memory, or artifacts when a reference suffices.

Redaction happens before telemetry export. Allowlisted fields, data classification, size caps, sampling, and automated secret-canary tests provide defense in depth.

## Events and state

Canonical state transitions emit domain events after commitment through an outbox or equivalent. Telemetry loss must not lose or change business state. Conversely, logs do not prove an external action succeeded; a Tool receipt/reconciliation record does.

## User and operator views

- **User trace:** task, responsible agent/version, progress, evidence, tools and outcomes, approvals, artifacts, costs, evaluation, concise failure/recovery options.
- **Operator view:** queues/workers, dependency/provider health, retries, rate limits, leases, detailed sanitized errors, policy versions, and alert correlation.
- **Security/audit view:** actors, grants, sensitive operations, payload digest/receipt references, and administrative actions.

All views omit chain-of-thought and enforce workspace/resource authorization.

## Service objectives and alerts

Stage 1/2 establishes baselines before numeric production SLOs. Candidate indicators include accepted-command availability, time to durable acceptance, queue age, execution terminalization, cancellation latency, tool success/unknown outcome, trace completeness, policy-check failure, and knowledge freshness. Alerts must be actionable, owned, and tied to a runbook; cost/runaway and cross-workspace/security signals receive urgent paths.

## Retention and cost

Define separate retention for canonical traces, audit events, debug logs, metrics, payload/artifact references, and evaluations. Sampling may reduce verbose successful telemetry but never remove required audit records or canonical state. Users need transparent retention/deletion behavior.

## Validation

Automated tests assert correlation propagation, redaction, bounded metric cardinality, valid state transitions in events, and trace completeness under success, retry, cancellation, timeout, approval, and worker-loss scenarios.
