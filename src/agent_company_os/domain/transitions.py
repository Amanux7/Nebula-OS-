"""Explicit append-only lifecycle transition records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from agent_company_os.domain.ids import StateTransitionId, Version, WorkspaceId
from agent_company_os.domain.validation import clean_required_text, require_utc


class SubjectType(StrEnum):
    KNOWLEDGE_SOURCE = "knowledge_source"
    AGENT_RUN = "agent_run"
    GOAL = "goal"
    TASK = "task"
    TASK_ATTEMPT = "task_attempt"
    EXECUTION = "execution"
    WORKSPACE = "workspace"


@dataclass(frozen=True, slots=True)
class StateTransition:
    id: StateTransitionId
    workspace_id: WorkspaceId
    subject_type: SubjectType
    subject_id: str
    previous_status: str
    new_status: str
    reason: str
    from_version: Version
    to_version: Version
    occurred_at: datetime

    def __post_init__(self) -> None:
        clean_required_text(self.subject_id, "subject_id")
        clean_required_text(self.previous_status, "previous_status")
        clean_required_text(self.new_status, "new_status")
        clean_required_text(self.reason, "reason")
        require_utc(self.occurred_at, "occurred_at")
        if self.to_version != self.from_version.next():
            from agent_company_os.domain.errors import InvariantViolation

            raise InvariantViolation(
                "transition_version_increment",
                details={
                    "from_version": str(self.from_version.value),
                    "to_version": str(self.to_version.value),
                },
            )


@dataclass(frozen=True, slots=True)
class TransitionResult[TEntity]:
    entity: TEntity
    transition: StateTransition
