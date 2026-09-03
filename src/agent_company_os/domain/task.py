"""Task logical-work aggregate and approved Stage 0.1 lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from agent_company_os.domain.errors import InvalidStateTransition
from agent_company_os.domain.ids import GoalId, StateTransitionId, TaskId, Version, WorkspaceId
from agent_company_os.domain.transitions import StateTransition, SubjectType, TransitionResult
from agent_company_os.domain.validation import (
    clean_required_text,
    clean_required_texts,
    require_monotonic_time,
    require_utc,
)


class TaskStatus(StrEnum):
    PROPOSED = "proposed"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Task:
    id: TaskId
    workspace_id: WorkspaceId
    goal_id: GoalId
    title: str
    acceptance_criteria: tuple[str, ...]
    status: TaskStatus
    version: Version
    created_at: datetime
    updated_at: datetime

    _ALLOWED: ClassVar[dict[TaskStatus, frozenset[TaskStatus]]] = {
        TaskStatus.PROPOSED: frozenset({TaskStatus.READY, TaskStatus.CANCELLED}),
        TaskStatus.READY: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
        TaskStatus.IN_PROGRESS: frozenset(
            {
                TaskStatus.COMPLETED,
                TaskStatus.READY,
                TaskStatus.BLOCKED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            }
        ),
        TaskStatus.BLOCKED: frozenset({TaskStatus.READY, TaskStatus.FAILED, TaskStatus.CANCELLED}),
        TaskStatus.COMPLETED: frozenset(),
        TaskStatus.FAILED: frozenset(),
        TaskStatus.CANCELLED: frozenset(),
    }

    def __post_init__(self) -> None:
        clean_required_text(self.title, "title")
        clean_required_texts(self.acceptance_criteria, "acceptance_criteria")
        require_utc(self.created_at, "created_at")
        require_utc(self.updated_at, "updated_at")

    @classmethod
    def create(
        cls,
        task_id: TaskId,
        workspace_id: WorkspaceId,
        goal_id: GoalId,
        title: str,
        acceptance_criteria: tuple[str, ...],
        created_at: datetime,
    ) -> Task:
        return cls(
            id=task_id,
            workspace_id=workspace_id,
            goal_id=goal_id,
            title=clean_required_text(title, "title"),
            acceptance_criteria=clean_required_texts(acceptance_criteria, "acceptance_criteria"),
            status=TaskStatus.PROPOSED,
            version=Version.initial(),
            created_at=created_at,
            updated_at=created_at,
        )

    def mark_ready(self, transition_id: StateTransitionId, at: datetime) -> TransitionResult[Task]:
        reason = "accept_work_definition" if self.status is TaskStatus.PROPOSED else "retry_ready"
        return self._transition(TaskStatus.READY, transition_id, at, reason)

    def start(self, transition_id: StateTransitionId, at: datetime) -> TransitionResult[Task]:
        return self._transition(TaskStatus.IN_PROGRESS, transition_id, at, "start_attempt")

    def complete(self, transition_id: StateTransitionId, at: datetime) -> TransitionResult[Task]:
        return self._transition(TaskStatus.COMPLETED, transition_id, at, "accept_result")

    def block(self, transition_id: StateTransitionId, at: datetime) -> TransitionResult[Task]:
        return self._transition(TaskStatus.BLOCKED, transition_id, at, "block")

    def fail(self, transition_id: StateTransitionId, at: datetime) -> TransitionResult[Task]:
        return self._transition(TaskStatus.FAILED, transition_id, at, "close_unsuccessful")

    def cancel(self, transition_id: StateTransitionId, at: datetime) -> TransitionResult[Task]:
        return self._transition(TaskStatus.CANCELLED, transition_id, at, "cancel")

    def _transition(
        self,
        target: TaskStatus,
        transition_id: StateTransitionId,
        at: datetime,
        reason: str,
    ) -> TransitionResult[Task]:
        if target not in self._ALLOWED[self.status]:
            raise InvalidStateTransition("Task", str(self.id), self.status.value, target.value)
        require_monotonic_time(self.updated_at, at, "transition_at")
        next_version = self.version.next()
        updated = replace(self, status=target, version=next_version, updated_at=at)
        transition = StateTransition(
            id=transition_id,
            workspace_id=self.workspace_id,
            subject_type=SubjectType.TASK,
            subject_id=str(self.id),
            previous_status=self.status.value,
            new_status=target.value,
            reason=reason,
            from_version=self.version,
            to_version=next_version,
            occurred_at=at,
        )
        return TransitionResult(updated, transition)
