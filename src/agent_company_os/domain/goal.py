"""Goal outcome aggregate and approved Stage 0.1 lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from agent_company_os.domain.errors import InvalidStateTransition
from agent_company_os.domain.ids import GoalId, StateTransitionId, Version, WorkspaceId
from agent_company_os.domain.transitions import StateTransition, SubjectType, TransitionResult
from agent_company_os.domain.validation import (
    clean_optional_texts,
    clean_required_text,
    clean_required_texts,
    require_monotonic_time,
    require_utc,
)


class GoalStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SATISFIED = "satisfied"
    CLOSED_UNSATISFIED = "closed_unsatisfied"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Goal:
    id: GoalId
    workspace_id: WorkspaceId
    objective: str
    constraints: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    status: GoalStatus
    version: Version
    created_at: datetime
    updated_at: datetime

    _ALLOWED: ClassVar[dict[GoalStatus, frozenset[GoalStatus]]] = {
        GoalStatus.DRAFT: frozenset({GoalStatus.ACTIVE, GoalStatus.CANCELLED}),
        GoalStatus.ACTIVE: frozenset(
            {
                GoalStatus.SATISFIED,
                GoalStatus.CLOSED_UNSATISFIED,
                GoalStatus.CANCELLED,
            }
        ),
        GoalStatus.SATISFIED: frozenset(),
        GoalStatus.CLOSED_UNSATISFIED: frozenset(),
        GoalStatus.CANCELLED: frozenset(),
    }

    def __post_init__(self) -> None:
        clean_required_text(self.objective, "objective")
        clean_optional_texts(self.constraints, "constraints")
        clean_required_texts(self.acceptance_criteria, "acceptance_criteria")
        require_utc(self.created_at, "created_at")
        require_utc(self.updated_at, "updated_at")

    @classmethod
    def create(
        cls,
        goal_id: GoalId,
        workspace_id: WorkspaceId,
        objective: str,
        constraints: tuple[str, ...],
        acceptance_criteria: tuple[str, ...],
        created_at: datetime,
    ) -> Goal:
        return cls(
            id=goal_id,
            workspace_id=workspace_id,
            objective=clean_required_text(objective, "objective"),
            constraints=clean_optional_texts(constraints, "constraints"),
            acceptance_criteria=clean_required_texts(acceptance_criteria, "acceptance_criteria"),
            status=GoalStatus.DRAFT,
            version=Version.initial(),
            created_at=created_at,
            updated_at=created_at,
        )

    def activate(self, transition_id: StateTransitionId, at: datetime) -> TransitionResult[Goal]:
        return self._transition(GoalStatus.ACTIVE, transition_id, at, "activate")

    def satisfy(self, transition_id: StateTransitionId, at: datetime) -> TransitionResult[Goal]:
        return self._transition(GoalStatus.SATISFIED, transition_id, at, "accept_outcome")

    def close_unsatisfied(
        self, transition_id: StateTransitionId, at: datetime
    ) -> TransitionResult[Goal]:
        return self._transition(
            GoalStatus.CLOSED_UNSATISFIED,
            transition_id,
            at,
            "close_without_satisfaction",
        )

    def cancel(self, transition_id: StateTransitionId, at: datetime) -> TransitionResult[Goal]:
        return self._transition(GoalStatus.CANCELLED, transition_id, at, "cancel")

    def _transition(
        self,
        target: GoalStatus,
        transition_id: StateTransitionId,
        at: datetime,
        reason: str,
    ) -> TransitionResult[Goal]:
        if target not in self._ALLOWED[self.status]:
            raise InvalidStateTransition("Goal", str(self.id), self.status.value, target.value)
        require_monotonic_time(self.updated_at, at, "transition_at")
        next_version = self.version.next()
        updated = replace(self, status=target, version=next_version, updated_at=at)
        transition = StateTransition(
            id=transition_id,
            workspace_id=self.workspace_id,
            subject_type=SubjectType.GOAL,
            subject_id=str(self.id),
            previous_status=self.status.value,
            new_status=target.value,
            reason=reason,
            from_version=self.version,
            to_version=next_version,
            occurred_at=at,
        )
        return TransitionResult(updated, transition)
