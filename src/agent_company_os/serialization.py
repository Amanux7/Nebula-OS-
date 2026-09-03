"""Explicit application-boundary serialization."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from agent_company_os.domain.errors import DomainError
from agent_company_os.domain.events import Event
from agent_company_os.domain.execution import Execution
from agent_company_os.domain.goal import Goal
from agent_company_os.domain.ids import OpaqueId, Version
from agent_company_os.domain.task import Task
from agent_company_os.domain.task_attempt import TaskAttempt
from agent_company_os.domain.workspace import Workspace


def _value(value: OpaqueId | Version | StrEnum | datetime | str | int | None) -> object:
    if isinstance(value, OpaqueId):
        return value.value
    if isinstance(value, Version):
        return value.value
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def serialize_entity(
    entity: Workspace | Goal | Task | TaskAttempt | Execution,
) -> dict[str, Any]:
    if isinstance(entity, Workspace):
        return {
            "id": _value(entity.id),
            "name": entity.name,
            "status": _value(entity.status),
            "version": _value(entity.version),
            "created_at": _value(entity.created_at),
            "updated_at": _value(entity.updated_at),
        }
    if isinstance(entity, Goal):
        return {
            "id": _value(entity.id),
            "workspace_id": _value(entity.workspace_id),
            "objective": entity.objective,
            "constraints": list(entity.constraints),
            "acceptance_criteria": list(entity.acceptance_criteria),
            "status": _value(entity.status),
            "version": _value(entity.version),
            "created_at": _value(entity.created_at),
            "updated_at": _value(entity.updated_at),
        }
    if isinstance(entity, Task):
        return {
            "id": _value(entity.id),
            "workspace_id": _value(entity.workspace_id),
            "goal_id": _value(entity.goal_id),
            "title": entity.title,
            "acceptance_criteria": list(entity.acceptance_criteria),
            "status": _value(entity.status),
            "version": _value(entity.version),
            "created_at": _value(entity.created_at),
            "updated_at": _value(entity.updated_at),
        }
    if isinstance(entity, TaskAttempt):
        return {
            "id": _value(entity.id),
            "workspace_id": _value(entity.workspace_id),
            "task_id": _value(entity.task_id),
            "execution_id": _value(entity.execution_id),
            "ordinal": entity.ordinal,
            "previous_attempt_id": _value(entity.previous_attempt_id),
            "status": _value(entity.status),
            "version": _value(entity.version),
            "created_at": _value(entity.created_at),
            "updated_at": _value(entity.updated_at),
            "started_at": _value(entity.started_at),
            "ended_at": _value(entity.ended_at),
            "failure_reason": entity.failure_reason,
        }
    return {
        "id": _value(entity.id),
        "workspace_id": _value(entity.workspace_id),
        "goal_id": _value(entity.goal_id),
        "initiated_by": entity.initiated_by,
        "bounds": {"max_task_attempts": entity.bounds.max_task_attempts},
        "retry_of": _value(entity.retry_of),
        "status": _value(entity.status),
        "version": _value(entity.version),
        "created_at": _value(entity.created_at),
        "updated_at": _value(entity.updated_at),
        "started_at": _value(entity.started_at),
        "ended_at": _value(entity.ended_at),
        "failure_reason": entity.failure_reason,
    }


def serialize_event(event: Event) -> dict[str, Any]:
    return {
        "id": _value(event.id),
        "workspace_id": _value(event.workspace_id),
        "event_type": _value(event.event_type),
        "subject_type": _value(event.subject_type),
        "subject_id": event.subject_id,
        "entity_version": _value(event.entity_version),
        "occurred_at": _value(event.occurred_at),
        "metadata": dict(event.metadata),
        "schema_version": event.schema_version,
    }


def serialize_error(error: DomainError) -> dict[str, object]:
    return error.to_dict()
