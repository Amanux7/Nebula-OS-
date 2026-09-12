"""Explicit protected previews and bounded metadata projections; no payload logging."""

import json

from agent_company_os.domain.events import Event, EventType
from agent_company_os.domain.governance import DecisionKind, GovernedAction
from agent_company_os.domain.tools import ToolReceipt


def serialize_governed_action(
    record: GovernedAction, receipts: tuple[ToolReceipt, ...] = ()
) -> dict[str, object]:
    intent = record.intent
    receipt = next((r for r in receipts if r.invocation.id == record.invocation_id), None)
    outcome = (
        "not_executed"
        if record.invocation_id is None
        else "observed_success"
        if receipt is not None and receipt.output is not None
        else "observed_failure"
        if receipt is not None and receipt.remote_outcome == "observed_failure"
        else "outcome_unknown"
    )
    return {
        "schema_version": 1,
        "intent_id": str(intent.id),
        "workspace_id": str(intent.workspace_id),
        "goal_id": str(intent.goal_id),
        "task_id": str(intent.task_id),
        "execution_id": str(intent.execution_id),
        "agent_run_id": str(intent.run_id),
        "action_id": str(intent.action_id),
        "tool_id": str(intent.tool.definition.id),
        "tool_version": intent.tool.version.value,
        "operation": intent.tool.executor_kind.value,
        "arguments": json.loads(intent.arguments_json),
        "destination": intent.destination,
        "fingerprint": intent.fingerprint,
        "risk": intent.tool.definition.risk.value,
        "policy_version": intent.policy.version.value,
        "effect": intent.effect.value,
        "created_at": intent.created_at.isoformat(),
        "expires_at": intent.expires_at.isoformat(),
        "preview": record.request.preview if record.request else None,
        "decisions": [
            {
                "kind": d.kind.value,
                "reviewer_id": str(d.reviewer.id) if d.reviewer else None,
                "at": d.at.isoformat(),
                "fingerprint": d.fingerprint,
                "policy_version": d.policy_version.value,
                "reason": d.reason,
            }
            for d in record.decisions
        ],
        "cancelled": record.cancelled,
        "claimed_invocation_id": str(record.invocation_id) if record.invocation_id else None,
        "receipt_id": str(receipt.id) if receipt else None,
        "consumed": record.consumed,
        "outcome": outcome,
        "version": record.version.value,
    }


def governance_metrics(
    records: tuple[GovernedAction, ...], events: tuple[Event, ...]
) -> dict[str, int | float]:
    requests = sum(r.request is not None for r in records)

    def count(kind: DecisionKind) -> int:
        return sum(any(d.kind is kind for d in r.decisions) for r in records)

    approved = count(DecisionKind.APPROVED)
    delays = [
        (d.at - r.intent.created_at).total_seconds()
        for r in records
        for d in r.decisions
        if d.kind is DecisionKind.APPROVED
    ]
    return {
        "intent_count": len(records),
        "approval_required_count": requests,
        "approval_rate": approved / requests if requests else 0,
        "rejection_rate": count(DecisionKind.REJECTED) / requests if requests else 0,
        "expiry_rate": count(DecisionKind.EXPIRED) / requests if requests else 0,
        "revocation_rate": count(DecisionKind.REVOKED) / requests if requests else 0,
        "time_to_approval_seconds_mean": sum(delays) / len(delays) if delays else 0,
        "execution_after_approval_rate": sum(
            r.invocation_id is not None and r.request is not None for r in records
        )
        / approved
        if approved
        else 0,
        "duplicate_replay_prevention_count": sum(
            e.event_type is EventType.ACTION_EXECUTION_DENIED
            and ("reason", "replay_prevented") in e.metadata
            for e in events
        ),
        "revalidation_rejection_count": sum(
            e.event_type is EventType.ACTION_EXECUTION_DENIED
            and ("reason", "revalidation_failed") in e.metadata
            for e in events
        ),
    }
