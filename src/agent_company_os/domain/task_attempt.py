"""A historical attempt to perform one logical Task."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from agent_company_os.domain.errors import InvalidStateTransition, InvariantViolation
from agent_company_os.domain.ids import (
    ExecutionId,
    StateTransitionId,
    TaskAttemptId,
    TaskId,
    Version,
    WorkspaceId,
)
from agent_company_os.domain.transitions import StateTransition, SubjectType, TransitionResult
from agent_company_os.domain.validation import (
    clean_required_text,
    require_monotonic_time,
    require_utc,
)


class TaskAttemptStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class TaskAttempt:
    id: TaskAttemptId
    workspace_id: WorkspaceId
    task_id: TaskId
    execution_id: ExecutionId
    ordinal: int
    previous_attempt_id: TaskAttemptId | None
    status: TaskAttemptStatus
    version: Version
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    failure_reason: str | None = None

    _ALLOWED: ClassVar[dict[TaskAttemptStatus, frozenset[TaskAttemptStatus]]] = {
        TaskAttemptStatus.CREATED: frozenset(
            {TaskAttemptStatus.RUNNING, TaskAttemptStatus.CANCELLED}
        ),
        TaskAttemptStatus.RUNNING: frozenset(
            {
                TaskAttemptStatus.SUCCEEDED,
                TaskAttemptStatus.FAILED,
                TaskAttemptStatus.CANCELLED,
            }
        ),
        TaskAttemptStatus.SUCCEEDED: frozenset(),
        TaskAttemptStatus.FAILED: frozenset(),
        TaskAttemptStatus.CANCELLED: frozenset(),
    }

    def __post_init__(self) -> None:
        if self.ordinal < 1:
            raise InvariantViolation("task_attempt_ordinal_positive")
        if (self.ordinal == 1) != (self.previous_attempt_id is None):
            raise InvariantViolation("task_attempt_retry_link_matches_ordinal")
        require_utc(self.created_at, "created_at")
        require_utc(self.updated_at, "updated_at")
        if self.started_at is not None:
            require_utc(self.started_at, "started_at")
        if self.ended_at is not None:
            require_utc(self.ended_at, "ended_at")
        if self.failure_reason is not None:
            clean_required_text(self.failure_reason, "failure_reason")

    @classmethod
    def create(
        cls,
        attempt_id: TaskAttemptId,
        workspace_id: WorkspaceId,
        task_id: TaskId,
        execution_id: ExecutionId,
        ordinal: int,
        previous_attempt_id: TaskAttemptId | None,
        created_at: datetime,
    ) -> TaskAttempt:
        return cls(
            id=attempt_id,
            workspace_id=workspace_id,
            task_id=task_id,
            execution_id=execution_id,
            ordinal=ordinal,
            previous_attempt_id=previous_attempt_id,
            status=TaskAttemptStatus.CREATED,
            version=Version.initial(),
            created_at=created_at,
            updated_at=created_at,
        )

    def start(
        self, transition_id: StateTransitionId, at: datetime
    ) -> TransitionResult[TaskAttempt]:
        return self._transition(TaskAttemptStatus.RUNNING, transition_id, at, "start")

    def succeed(
        self, transition_id: StateTransitionId, at: datetime
    ) -> TransitionResult[TaskAttempt]:
        return self._transition(TaskAttemptStatus.SUCCEEDED, transition_id, at, "result_accepted")

    def fail(
        self, transition_id: StateTransitionId, at: datetime, reason: str
    ) -> TransitionResult[TaskAttempt]:
        clean_required_text(reason, "failure_reason")
        return self._transition(TaskAttemptStatus.FAILED, transition_id, at, reason)

    def cancel(
        self, transition_id: StateTransitionId, at: datetime
    ) -> TransitionResult[TaskAttempt]:
        return self._transition(TaskAttemptStatus.CANCELLED, transition_id, at, "cancel")

    def _transition(
        self,
        target: TaskAttemptStatus,
        transition_id: StateTransitionId,
        at: datetime,
        reason: str,
    ) -> TransitionResult[TaskAttempt]:
        if target not in self._ALLOWED[self.status]:
            raise InvalidStateTransition(
                "TaskAttempt", str(self.id), self.status.value, target.value
            )
        require_monotonic_time(self.updated_at, at, "transition_at")
        next_version = self.version.next()
        updated = replace(
            self,
            status=target,
            version=next_version,
            updated_at=at,
            started_at=at if target is TaskAttemptStatus.RUNNING else self.started_at,
            ended_at=at if target in self.terminal_statuses() else self.ended_at,
            failure_reason=reason if target is TaskAttemptStatus.FAILED else self.failure_reason,
        )
        transition = StateTransition(
            id=transition_id,
            workspace_id=self.workspace_id,
            subject_type=SubjectType.TASK_ATTEMPT,
            subject_id=str(self.id),
            previous_status=self.status.value,
            new_status=target.value,
            reason=reason,
            from_version=self.version,
            to_version=next_version,
            occurred_at=at,
        )
        return TransitionResult(updated, transition)

    @staticmethod
    def terminal_statuses() -> frozenset[TaskAttemptStatus]:
        return frozenset(
            {
                TaskAttemptStatus.SUCCEEDED,
                TaskAttemptStatus.FAILED,
                TaskAttemptStatus.CANCELLED,
            }
        )
