"""Random production IDs and predictable test IDs."""

from collections import defaultdict
from uuid import uuid4

from agent_company_os.domain.agent import ActionId, AgentRunId, ObservationId
from agent_company_os.domain.ids import (
    EventId,
    ExecutionId,
    GoalId,
    StateTransitionId,
    TaskAttemptId,
    TaskId,
    WorkspaceId,
)


class SystemIdGenerator:
    def agent_run_id(self) -> AgentRunId:
        return AgentRunId(str(uuid4()))

    def action_id(self) -> ActionId:
        return ActionId(str(uuid4()))

    def observation_id(self) -> ObservationId:
        return ObservationId(str(uuid4()))

    def workspace_id(self) -> WorkspaceId:
        return WorkspaceId(str(uuid4()))

    def goal_id(self) -> GoalId:
        return GoalId(str(uuid4()))

    def task_id(self) -> TaskId:
        return TaskId(str(uuid4()))

    def task_attempt_id(self) -> TaskAttemptId:
        return TaskAttemptId(str(uuid4()))

    def execution_id(self) -> ExecutionId:
        return ExecutionId(str(uuid4()))

    def event_id(self) -> EventId:
        return EventId(str(uuid4()))

    def state_transition_id(self) -> StateTransitionId:
        return StateTransitionId(str(uuid4()))


class DeterministicIdGenerator:
    def agent_run_id(self) -> AgentRunId:
        return AgentRunId(self._next("agent-run"))

    def action_id(self) -> ActionId:
        return ActionId(self._next("action"))

    def observation_id(self) -> ObservationId:
        return ObservationId(self._next("observation"))

    def __init__(self, prefix: str = "test") -> None:
        self._prefix = prefix
        self._counts: defaultdict[str, int] = defaultdict(int)

    def _next(self, kind: str) -> str:
        self._counts[kind] += 1
        return f"{self._prefix}-{kind}-{self._counts[kind]:04d}"

    def workspace_id(self) -> WorkspaceId:
        return WorkspaceId(self._next("workspace"))

    def goal_id(self) -> GoalId:
        return GoalId(self._next("goal"))

    def task_id(self) -> TaskId:
        return TaskId(self._next("task"))

    def task_attempt_id(self) -> TaskAttemptId:
        return TaskAttemptId(self._next("attempt"))

    def execution_id(self) -> ExecutionId:
        return ExecutionId(self._next("execution"))

    def event_id(self) -> EventId:
        return EventId(self._next("event"))

    def state_transition_id(self) -> StateTransitionId:
        return StateTransitionId(self._next("transition"))
