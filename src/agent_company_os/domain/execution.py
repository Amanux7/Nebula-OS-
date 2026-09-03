"""Bounded deterministic execution bookkeeping."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from agent_company_os.domain.errors import InvalidStateTransition, InvariantViolation
from agent_company_os.domain.ids import (
    ExecutionId,
    GoalId,
    StateTransitionId,
    Version,
    WorkspaceId,
)
from agent_company_os.domain.transitions import StateTransition, SubjectType, TransitionResult
from agent_company_os.domain.validation import (
    clean_required_text,
    require_monotonic_time,
    require_utc,
)


class ExecutionStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ExecutionBounds:
    max_task_attempts: int

    def __post_init__(self) -> None:
        if self.max_task_attempts < 1:
            raise InvariantViolation("execution_max_task_attempts_positive")


@dataclass(frozen=True, slots=True)
class Execution:
    id: ExecutionId
    workspace_id: WorkspaceId
    goal_id: GoalId
    initiated_by: str
    bounds: ExecutionBounds
    retry_of: ExecutionId | None
    status: ExecutionStatus
    version: Version
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    failure_reason: str | None = None

    _ALLOWED: ClassVar[dict[ExecutionStatus, frozenset[ExecutionStatus]]] = {
        ExecutionStatus.CREATED: frozenset({ExecutionStatus.RUNNING, ExecutionStatus.CANCELLED}),
        ExecutionStatus.RUNNING: frozenset(
            {
                ExecutionStatus.WAITING,
                ExecutionStatus.SUCCEEDED,
                ExecutionStatus.FAILED,
                ExecutionStatus.CANCELLED,
            }
        ),
        ExecutionStatus.WAITING: frozenset(
            {
                ExecutionStatus.RUNNING,
                ExecutionStatus.FAILED,
                ExecutionStatus.CANCELLED,
            }
        ),
        ExecutionStatus.SUCCEEDED: frozenset(),
        ExecutionStatus.FAILED: frozenset(),
        ExecutionStatus.CANCELLED: frozenset(),
    }

    def __post_init__(self) -> None:
        clean_required_text(self.initiated_by, "initiated_by")
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
        execution_id: ExecutionId,
        workspace_id: WorkspaceId,
        goal_id: GoalId,
        initiated_by: str,
        bounds: ExecutionBounds,
        retry_of: ExecutionId | None,
        created_at: datetime,
    ) -> Execution:
        return cls(
            id=execution_id,
            workspace_id=workspace_id,
            goal_id=goal_id,
            initiated_by=clean_required_text(initiated_by, "initiated_by"),
            bounds=bounds,
            retry_of=retry_of,
            status=ExecutionStatus.CREATED,
            version=Version.initial(),
            created_at=created_at,
            updated_at=created_at,
        )

    def start(self, transition_id: StateTransitionId, at: datetime) -> TransitionResult[Execution]:
        return self._transition(ExecutionStatus.RUNNING, transition_id, at, "start")

    def wait(self, transition_id: StateTransitionId, at: datetime) -> TransitionResult[Execution]:
        return self._transition(ExecutionStatus.WAITING, transition_id, at, "wait")

    def resume(self, transition_id: StateTransitionId, at: datetime) -> TransitionResult[Execution]:
        return self._transition(ExecutionStatus.RUNNING, transition_id, at, "resume")

    def succeed(
        self, transition_id: StateTransitionId, at: datetime
    ) -> TransitionResult[Execution]:
        return self._transition(ExecutionStatus.SUCCEEDED, transition_id, at, "complete")

    def fail(
        self, transition_id: StateTransitionId, at: datetime, reason: str
    ) -> TransitionResult[Execution]:
        clean_required_text(reason, "failure_reason")
        return self._transition(ExecutionStatus.FAILED, transition_id, at, reason)

    def cancel(self, transition_id: StateTransitionId, at: datetime) -> TransitionResult[Execution]:
        return self._transition(ExecutionStatus.CANCELLED, transition_id, at, "cancel")

    def _transition(
        self,
        target: ExecutionStatus,
        transition_id: StateTransitionId,
        at: datetime,
        reason: str,
    ) -> TransitionResult[Execution]:
        if target not in self._ALLOWED[self.status]:
            raise InvalidStateTransition("Execution", str(self.id), self.status.value, target.value)
        require_monotonic_time(self.updated_at, at, "transition_at")
        next_version = self.version.next()
        updated = replace(
            self,
            status=target,
            version=next_version,
            updated_at=at,
            started_at=at
            if self.started_at is None and target is ExecutionStatus.RUNNING
            else self.started_at,
            ended_at=at if target in self.terminal_statuses() else self.ended_at,
            failure_reason=reason if target is ExecutionStatus.FAILED else self.failure_reason,
        )
        transition = StateTransition(
            id=transition_id,
            workspace_id=self.workspace_id,
            subject_type=SubjectType.EXECUTION,
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
    def terminal_statuses() -> frozenset[ExecutionStatus]:
        return frozenset(
            {ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}
        )
