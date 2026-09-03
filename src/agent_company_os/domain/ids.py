"""Opaque identifiers and optimistic concurrency versions."""

from __future__ import annotations

from dataclasses import dataclass

from agent_company_os.domain.errors import InvariantViolation


@dataclass(frozen=True, slots=True)
class OpaqueId:
    """Serializable identifier whose concrete subclass carries entity type."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value.strip() != self.value:
            raise InvariantViolation(
                "identifier_non_empty",
                details={"identifier_type": type(self).__name__},
            )

    def __str__(self) -> str:
        return self.value


class WorkspaceId(OpaqueId):
    """Workspace identifier."""


class GoalId(OpaqueId):
    """Goal identifier."""


class TaskId(OpaqueId):
    """Task identifier."""


class TaskAttemptId(OpaqueId):
    """TaskAttempt identifier."""


class ExecutionId(OpaqueId):
    """Execution identifier."""


class EventId(OpaqueId):
    """Event identifier."""


class StateTransitionId(OpaqueId):
    """StateTransition identifier."""


@dataclass(frozen=True, order=True, slots=True)
class Version:
    """Positive optimistic concurrency token."""

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or self.value < 1:
            raise InvariantViolation(
                "version_positive_integer",
                details={"value": str(self.value)},
            )

    @classmethod
    def initial(cls) -> Version:
        return cls(1)

    def next(self) -> Version:
        return Version(self.value + 1)
