"""Explicit JSON-safe communication representations."""

from agent_company_os.domain.communication import (
    AgentMessage,
    HandoffRequest,
    HandoffRequestPayload,
    HandoffResultPayload,
    InformationPayload,
    MessagePayload,
    MessageThread,
    RequestPayload,
    ResponsePayload,
)


def _payload(payload: MessagePayload) -> dict[str, object]:
    if isinstance(payload, (InformationPayload, ResponsePayload)):
        return {"summary": payload.summary, "items": list(payload.items)}
    if isinstance(payload, RequestPayload):
        return {
            "request_type": payload.request_type,
            "question": payload.question,
            "expected_response": payload.expected_response,
            "substantial_work": payload.substantial_work,
        }
    if isinstance(payload, HandoffRequestPayload):
        requirements = payload.target_requirements
        return {
            "reason_code": payload.reason_code,
            "summary": payload.summary,
            "target_requirements": {
                "capabilities": list(requirements.capabilities),
                "capability_ids": [str(c) for c in requirements.capability_ids],
                "required_department": str(requirements.required_department)
                if requirements.required_department
                else None,
                "preferred_department": str(requirements.preferred_department)
                if requirements.preferred_department
                else None,
                "organizational_role": str(requirements.organizational_role)
                if requirements.organizational_role
                else None,
                "tool_ids": [str(item) for item in requirements.tool_ids],
                "knowledge_source_ids": [str(item) for item in requirements.knowledge_source_ids],
                "memory_scopes": [
                    {"kind": item.kind.value, "key": item.key}
                    for item in requirements.memory_scopes
                ],
                "min_autonomy": requirements.min_autonomy,
            },
        }
    assert isinstance(payload, HandoffResultPayload)
    return {
        "summary": payload.summary,
        "task_result_reference": payload.task_result_reference,
    }


def _references(message: AgentMessage) -> list[dict[str, object]]:
    return [
        {
            "kind": item.kind.value,
            "reference_id": item.reference_id,
            "workspace_id": str(item.workspace_id),
            "source_agent_run_id": str(item.source_agent_run_id),
        }
        for item in message.references
    ]


def serialize_message(message: AgentMessage) -> dict[str, object]:
    return {
        "schema_version": message.schema_version,
        "id": str(message.id),
        "workspace_id": str(message.workspace_id),
        "orchestration_run_id": str(message.orchestration_run_id),
        "thread_id": str(message.thread_id),
        "sender_agent_run_id": str(message.sender_agent_run_id),
        "sender_definition_id": str(message.sender_definition_id),
        "sender_definition_version": message.sender_definition_version.value,
        "recipient_agent_run_id": str(message.recipient_agent_run_id),
        "recipient_definition_id": str(message.recipient_definition_id),
        "recipient_definition_version": message.recipient_definition_version.value,
        "sender_task_id": str(message.sender_task_id),
        "sender_delegation_id": str(message.sender_delegation_id),
        "recipient_task_id": str(message.recipient_task_id),
        "recipient_delegation_id": str(message.recipient_delegation_id),
        "kind": message.kind.value,
        "payload": _payload(message.payload),
        "references": _references(message),
        "correlation_id": message.correlation_id,
        "in_reply_to": str(message.in_reply_to) if message.in_reply_to else None,
        "status": message.status.value,
        "version": message.version.value,
        "created_at": message.created_at.isoformat(),
        "deadline": message.deadline.isoformat(),
        "delivered_at": message.delivered_at.isoformat() if message.delivered_at else None,
        "ended_at": message.ended_at.isoformat() if message.ended_at else None,
        "status_reason": message.status_reason,
        "policy_version": message.policy_version,
    }


def serialize_thread(thread: MessageThread) -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": str(thread.id),
        "workspace_id": str(thread.workspace_id),
        "orchestration_run_id": str(thread.orchestration_run_id),
        "subject": thread.subject,
        "created_by": str(thread.created_by),
        "created_at": thread.created_at.isoformat(),
        "status": thread.status.value,
        "version": thread.version.value,
    }


def serialize_handoff(handoff: HandoffRequest) -> dict[str, object]:
    return {
        "schema_version": handoff.schema_version,
        "id": str(handoff.id),
        "workspace_id": str(handoff.workspace_id),
        "orchestration_run_id": str(handoff.orchestration_run_id),
        "sender_agent_run_id": str(handoff.sender_agent_run_id),
        "sender_definition_id": str(handoff.sender_definition_id),
        "sender_definition_version": handoff.sender_definition_version.value,
        "source_task_id": str(handoff.source_task_id),
        "source_delegation_id": str(handoff.source_delegation_id),
        "payload": _payload(handoff.payload),
        "references": [
            {
                "kind": item.kind.value,
                "reference_id": item.reference_id,
                "workspace_id": str(item.workspace_id),
                "source_agent_run_id": str(item.source_agent_run_id),
            }
            for item in handoff.references
        ],
        "depth": handoff.depth,
        "parent_handoff_id": str(handoff.parent_handoff_id) if handoff.parent_handoff_id else None,
        "status": handoff.status.value,
        "version": handoff.version.value,
        "recipient_definition_id": str(handoff.recipient_definition_id)
        if handoff.recipient_definition_id
        else None,
        "recipient_definition_version": handoff.recipient_definition_version.value
        if handoff.recipient_definition_version
        else None,
        "resulting_delegation_id": str(handoff.resulting_delegation_id)
        if handoff.resulting_delegation_id
        else None,
        "result_reference": handoff.result_reference,
        "created_at": handoff.created_at.isoformat(),
        "deadline": handoff.deadline.isoformat(),
        "ended_at": handoff.ended_at.isoformat() if handoff.ended_at else None,
        "status_reason": handoff.status_reason,
        "policy_version": handoff.policy_version,
    }
