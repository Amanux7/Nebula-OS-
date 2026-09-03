"""Typed application boundary coordinating domain behavior and persistence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from agent_company_os.domain.errors import InvariantViolation, VersionConflict, WorkspaceMismatch
from agent_company_os.domain.events import Event, EventType
from agent_company_os.domain.execution import Execution, ExecutionBounds, ExecutionStatus
from agent_company_os.domain.goal import Goal, GoalStatus
from agent_company_os.domain.ids import (
    ExecutionId,
    GoalId,
    TaskAttemptId,
    TaskId,
    Version,
    WorkspaceId,
)
from agent_company_os.domain.task import Task, TaskStatus
from agent_company_os.domain.task_attempt import TaskAttempt, TaskAttemptStatus
from agent_company_os.domain.transitions import SubjectType, TransitionResult
from agent_company_os.domain.workspace import Workspace
from agent_company_os.ports.clock import Clock
from agent_company_os.ports.ids import IdGenerator
from agent_company_os.ports.store import DomainStore


@dataclass(frozen=True, slots=True)
class CreateGoalCommand:
    workspace_id: WorkspaceId
    objective: str
    acceptance_criteria: tuple[str, ...]
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CreateTaskCommand:
    workspace_id: WorkspaceId
    goal_id: GoalId
    title: str
    acceptance_criteria: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CreateExecutionCommand:
    workspace_id: WorkspaceId
    goal_id: GoalId
    initiated_by: str
    max_task_attempts: int
    retry_of: ExecutionId | None = None


@dataclass(frozen=True, slots=True)
class CreateTaskAttemptCommand:
    workspace_id: WorkspaceId
    task_id: TaskId
    execution_id: ExecutionId


class DomainService:
    def __init__(self, store: DomainStore, clock: Clock, ids: IdGenerator) -> None:
        self.store = store
        self.clock = clock
        self.ids = ids

    def create_workspace(self, name: str) -> Workspace:
        now = self.clock.now()
        workspace = Workspace.create(self.ids.workspace_id(), name, now)
        self.store.add_workspace(
            workspace,
            self._event(
                workspace.id,
                EventType.WORKSPACE_CREATED,
                SubjectType.WORKSPACE,
                str(workspace.id),
                workspace.version,
            ),
        )
        return workspace

    def create_goal(self, command: CreateGoalCommand) -> Goal:
        self.store.get_workspace(command.workspace_id)
        now = self.clock.now()
        goal = Goal.create(
            self.ids.goal_id(),
            command.workspace_id,
            command.objective,
            command.constraints,
            command.acceptance_criteria,
            now,
        )
        self.store.add_goal(
            goal,
            self._event(
                goal.workspace_id,
                EventType.GOAL_CREATED,
                SubjectType.GOAL,
                str(goal.id),
                goal.version,
            ),
        )
        return goal

    def activate_goal(self, goal_id: GoalId, expected_version: Version) -> Goal:
        goal = self.store.get_goal(goal_id)
        self._expect_version("Goal", str(goal.id), expected_version, goal.version)
        result = goal.activate(self.ids.state_transition_id(), self.clock.now())
        return self._save_goal(result, expected_version, EventType.GOAL_ACTIVATED)

    def satisfy_goal(self, goal_id: GoalId, expected_version: Version) -> Goal:
        goal = self.store.get_goal(goal_id)
        self._expect_version("Goal", str(goal.id), expected_version, goal.version)
        tasks = self.store.tasks_for_goal(goal.id)
        if not tasks or any(task.status is not TaskStatus.COMPLETED for task in tasks):
            raise InvariantViolation("goal_satisfaction_requires_all_tasks_completed")
        result = goal.satisfy(self.ids.state_transition_id(), self.clock.now())
        return self._save_goal(result, expected_version, EventType.GOAL_SATISFIED)

    def close_goal_unsatisfied(self, goal_id: GoalId, expected_version: Version) -> Goal:
        goal = self.store.get_goal(goal_id)
        self._expect_version("Goal", str(goal.id), expected_version, goal.version)
        result = goal.close_unsatisfied(self.ids.state_transition_id(), self.clock.now())
        return self._save_goal(result, expected_version, EventType.GOAL_CLOSED_UNSATISFIED)

    def cancel_goal(self, goal_id: GoalId, expected_version: Version) -> Goal:
        goal = self.store.get_goal(goal_id)
        self._expect_version("Goal", str(goal.id), expected_version, goal.version)
        result = goal.cancel(self.ids.state_transition_id(), self.clock.now())
        return self._save_goal(result, expected_version, EventType.GOAL_CANCELLED)

    def create_task(self, command: CreateTaskCommand) -> Task:
        self.store.get_workspace(command.workspace_id)
        goal = self.store.get_goal(command.goal_id)
        self._same_workspace("Task.goal", command.workspace_id, goal.workspace_id)
        if goal.status is not GoalStatus.ACTIVE:
            raise InvariantViolation("task_creation_requires_active_goal")
        now = self.clock.now()
        task = Task.create(
            self.ids.task_id(),
            command.workspace_id,
            command.goal_id,
            command.title,
            command.acceptance_criteria,
            now,
        )
        self.store.add_task(
            task,
            self._event(
                task.workspace_id,
                EventType.TASK_CREATED,
                SubjectType.TASK,
                str(task.id),
                task.version,
            ),
        )
        return task

    def ready_task(self, task_id: TaskId, expected_version: Version) -> Task:
        task = self.store.get_task(task_id)
        self._expect_version("Task", str(task.id), expected_version, task.version)
        previous = task.status
        result = task.mark_ready(self.ids.state_transition_id(), self.clock.now())
        event_type = (
            EventType.TASK_READY if previous is TaskStatus.PROPOSED else EventType.TASK_RETRY_READY
        )
        return self._save_task(result, expected_version, event_type)

    def start_task(self, task_id: TaskId, expected_version: Version) -> Task:
        task = self.store.get_task(task_id)
        self._expect_version("Task", str(task.id), expected_version, task.version)
        return self._save_task(
            task.start(self.ids.state_transition_id(), self.clock.now()),
            expected_version,
            EventType.TASK_STARTED,
        )

    def complete_task(
        self, task_id: TaskId, attempt_id: TaskAttemptId, expected_version: Version
    ) -> Task:
        task = self.store.get_task(task_id)
        attempt = self.store.get_task_attempt(attempt_id)
        self._expect_version("Task", str(task.id), expected_version, task.version)
        self._same_workspace("Task.attempt", task.workspace_id, attempt.workspace_id)
        if attempt.task_id != task.id or attempt.status is not TaskAttemptStatus.SUCCEEDED:
            raise InvariantViolation("task_completion_requires_its_succeeded_attempt")
        return self._save_task(
            task.complete(self.ids.state_transition_id(), self.clock.now()),
            expected_version,
            EventType.TASK_COMPLETED,
        )

    def fail_task(self, task_id: TaskId, expected_version: Version) -> Task:
        task = self.store.get_task(task_id)
        self._expect_version("Task", str(task.id), expected_version, task.version)
        return self._save_task(
            task.fail(self.ids.state_transition_id(), self.clock.now()),
            expected_version,
            EventType.TASK_FAILED,
        )

    def cancel_task(self, task_id: TaskId, expected_version: Version) -> Task:
        task = self.store.get_task(task_id)
        self._expect_version("Task", str(task.id), expected_version, task.version)
        return self._save_task(
            task.cancel(self.ids.state_transition_id(), self.clock.now()),
            expected_version,
            EventType.TASK_CANCELLED,
        )

    def create_execution(self, command: CreateExecutionCommand) -> Execution:
        self.store.get_workspace(command.workspace_id)
        goal = self.store.get_goal(command.goal_id)
        self._same_workspace("Execution.goal", command.workspace_id, goal.workspace_id)
        if goal.status is not GoalStatus.ACTIVE:
            raise InvariantViolation("execution_creation_requires_active_goal")
        if command.retry_of is not None:
            previous = self.store.get_execution(command.retry_of)
            self._same_workspace("Execution.retry", command.workspace_id, previous.workspace_id)
            if previous.goal_id != goal.id or previous.status not in Execution.terminal_statuses():
                raise InvariantViolation("execution_retry_requires_terminal_execution_for_goal")
        now = self.clock.now()
        execution = Execution.create(
            self.ids.execution_id(),
            command.workspace_id,
            command.goal_id,
            command.initiated_by,
            ExecutionBounds(command.max_task_attempts),
            command.retry_of,
            now,
        )
        self.store.add_execution(
            execution,
            self._event(
                execution.workspace_id,
                EventType.EXECUTION_CREATED,
                SubjectType.EXECUTION,
                str(execution.id),
                execution.version,
            ),
        )
        return execution

    def start_execution(self, execution_id: ExecutionId, expected_version: Version) -> Execution:
        return self._change_execution(
            execution_id, expected_version, Execution.start, EventType.EXECUTION_STARTED
        )

    def wait_execution(self, execution_id: ExecutionId, expected_version: Version) -> Execution:
        return self._change_execution(
            execution_id, expected_version, Execution.wait, EventType.EXECUTION_WAITING
        )

    def resume_execution(self, execution_id: ExecutionId, expected_version: Version) -> Execution:
        return self._change_execution(
            execution_id, expected_version, Execution.resume, EventType.EXECUTION_RESUMED
        )

    def succeed_execution(self, execution_id: ExecutionId, expected_version: Version) -> Execution:
        execution = self.store.get_execution(execution_id)
        self._expect_version("Execution", str(execution.id), expected_version, execution.version)
        tasks = self.store.tasks_for_goal(execution.goal_id)
        attempts = self.store.attempts_for_execution(execution.id)
        if not tasks or any(task.status is not TaskStatus.COMPLETED for task in tasks):
            raise InvariantViolation("execution_success_requires_all_goal_tasks_completed")
        if any(attempt.status not in TaskAttempt.terminal_statuses() for attempt in attempts):
            raise InvariantViolation("execution_success_requires_terminal_attempts")
        return self._save_execution(
            execution.succeed(self.ids.state_transition_id(), self.clock.now()),
            expected_version,
            EventType.EXECUTION_SUCCEEDED,
        )

    def fail_execution(
        self, execution_id: ExecutionId, expected_version: Version, reason: str
    ) -> Execution:
        execution = self.store.get_execution(execution_id)
        self._expect_version("Execution", str(execution.id), expected_version, execution.version)
        result = execution.fail(self.ids.state_transition_id(), self.clock.now(), reason)
        return self._save_execution(result, expected_version, EventType.EXECUTION_FAILED)

    def cancel_execution(self, execution_id: ExecutionId, expected_version: Version) -> Execution:
        return self._change_execution(
            execution_id, expected_version, Execution.cancel, EventType.EXECUTION_CANCELLED
        )

    def create_task_attempt(self, command: CreateTaskAttemptCommand) -> TaskAttempt:
        self.store.get_workspace(command.workspace_id)
        task = self.store.get_task(command.task_id)
        execution = self.store.get_execution(command.execution_id)
        self._same_workspace("TaskAttempt.task", command.workspace_id, task.workspace_id)
        self._same_workspace("TaskAttempt.execution", command.workspace_id, execution.workspace_id)
        if task.goal_id != execution.goal_id:
            raise InvariantViolation("task_attempt_task_and_execution_share_goal")
        if task.status is not TaskStatus.IN_PROGRESS:
            raise InvariantViolation("task_attempt_creation_requires_in_progress_task")
        if execution.status is not ExecutionStatus.RUNNING:
            raise InvariantViolation("task_attempt_creation_requires_running_execution")
        attempts = self.store.attempts_for_task(task.id)
        if any(attempt.status not in TaskAttempt.terminal_statuses() for attempt in attempts):
            raise InvariantViolation("one_non_terminal_attempt_per_task")
        execution_attempts = self.store.attempts_for_execution(execution.id)
        if len(execution_attempts) >= execution.bounds.max_task_attempts:
            raise InvariantViolation("execution_task_attempt_bound")
        previous_id = attempts[-1].id if attempts else None
        now = self.clock.now()
        attempt = TaskAttempt.create(
            self.ids.task_attempt_id(),
            command.workspace_id,
            command.task_id,
            command.execution_id,
            len(attempts) + 1,
            previous_id,
            now,
        )
        self.store.add_task_attempt(
            attempt,
            self._event(
                attempt.workspace_id,
                EventType.TASK_ATTEMPT_CREATED,
                SubjectType.TASK_ATTEMPT,
                str(attempt.id),
                attempt.version,
            ),
        )
        return attempt

    def start_task_attempt(
        self, attempt_id: TaskAttemptId, expected_version: Version
    ) -> TaskAttempt:
        return self._change_attempt(
            attempt_id, expected_version, TaskAttempt.start, EventType.TASK_ATTEMPT_STARTED
        )

    def succeed_task_attempt(
        self, attempt_id: TaskAttemptId, expected_version: Version
    ) -> TaskAttempt:
        return self._change_attempt(
            attempt_id, expected_version, TaskAttempt.succeed, EventType.TASK_ATTEMPT_SUCCEEDED
        )

    def fail_task_attempt(
        self, attempt_id: TaskAttemptId, expected_version: Version, reason: str
    ) -> TaskAttempt:
        attempt = self.store.get_task_attempt(attempt_id)
        self._expect_version("TaskAttempt", str(attempt.id), expected_version, attempt.version)
        result = attempt.fail(self.ids.state_transition_id(), self.clock.now(), reason)
        return self._save_attempt(result, expected_version, EventType.TASK_ATTEMPT_FAILED)

    def cancel_task_attempt(
        self, attempt_id: TaskAttemptId, expected_version: Version
    ) -> TaskAttempt:
        return self._change_attempt(
            attempt_id, expected_version, TaskAttempt.cancel, EventType.TASK_ATTEMPT_CANCELLED
        )

    def _change_execution(
        self,
        execution_id: ExecutionId,
        expected_version: Version,
        operation: Callable[..., TransitionResult[Execution]],
        event_type: EventType,
    ) -> Execution:
        execution = self.store.get_execution(execution_id)
        self._expect_version("Execution", str(execution.id), expected_version, execution.version)
        result = operation(execution, self.ids.state_transition_id(), self.clock.now())
        return self._save_execution(result, expected_version, event_type)

    def _change_attempt(
        self,
        attempt_id: TaskAttemptId,
        expected_version: Version,
        operation: Callable[..., TransitionResult[TaskAttempt]],
        event_type: EventType,
    ) -> TaskAttempt:
        attempt = self.store.get_task_attempt(attempt_id)
        self._expect_version("TaskAttempt", str(attempt.id), expected_version, attempt.version)
        result = operation(attempt, self.ids.state_transition_id(), self.clock.now())
        return self._save_attempt(result, expected_version, event_type)

    def _save_goal(
        self, result: TransitionResult[Goal], expected_version: Version, event_type: EventType
    ) -> Goal:
        event = self._event_for_transition(result, event_type)
        self.store.save_goal(result.entity, expected_version, result.transition, event)
        return result.entity

    def _save_task(
        self, result: TransitionResult[Task], expected_version: Version, event_type: EventType
    ) -> Task:
        event = self._event_for_transition(result, event_type)
        self.store.save_task(result.entity, expected_version, result.transition, event)
        return result.entity

    def _save_attempt(
        self,
        result: TransitionResult[TaskAttempt],
        expected_version: Version,
        event_type: EventType,
    ) -> TaskAttempt:
        event = self._event_for_transition(result, event_type)
        self.store.save_task_attempt(result.entity, expected_version, result.transition, event)
        return result.entity

    def _save_execution(
        self,
        result: TransitionResult[Execution],
        expected_version: Version,
        event_type: EventType,
    ) -> Execution:
        event = self._event_for_transition(result, event_type)
        self.store.save_execution(result.entity, expected_version, result.transition, event)
        return result.entity

    def _event_for_transition[T: Goal | Task | TaskAttempt | Execution](
        self, result: TransitionResult[T], event_type: EventType
    ) -> Event:
        return self._event(
            result.transition.workspace_id,
            event_type,
            result.transition.subject_type,
            result.transition.subject_id,
            result.transition.to_version,
        )

    def _event(
        self,
        workspace_id: WorkspaceId,
        event_type: EventType,
        subject_type: SubjectType,
        subject_id: str,
        version: Version,
    ) -> Event:
        return Event(
            id=self.ids.event_id(),
            workspace_id=workspace_id,
            event_type=event_type,
            subject_type=subject_type,
            subject_id=subject_id,
            entity_version=version,
            occurred_at=self.clock.now(),
        )

    @staticmethod
    def _expect_version(
        entity_type: str, entity_id: str, expected: Version, actual: Version
    ) -> None:
        if expected != actual:
            raise VersionConflict(entity_type, entity_id, expected.value, actual.value)

    @staticmethod
    def _same_workspace(relationship: str, expected: WorkspaceId, actual: WorkspaceId) -> None:
        if expected != actual:
            raise WorkspaceMismatch(relationship, str(expected), str(actual))
