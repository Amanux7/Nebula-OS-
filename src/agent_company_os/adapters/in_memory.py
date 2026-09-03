"""Thread-safe deterministic in-memory persistence adapter."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import fields
from threading import RLock
from typing import TypeVar

from agent_company_os.domain.errors import (
    EntityNotFound,
    InvariantViolation,
    VersionConflict,
    WorkspaceMismatch,
)
from agent_company_os.domain.events import Event
from agent_company_os.domain.execution import Execution
from agent_company_os.domain.goal import Goal
from agent_company_os.domain.ids import (
    EventId,
    ExecutionId,
    GoalId,
    StateTransitionId,
    TaskAttemptId,
    TaskId,
    Version,
    WorkspaceId,
)
from agent_company_os.domain.task import Task
from agent_company_os.domain.task_attempt import TaskAttempt
from agent_company_os.domain.transitions import StateTransition
from agent_company_os.domain.workspace import Workspace

TId = TypeVar("TId")
TEntity = TypeVar("TEntity", bound=Workspace | Goal | Task | TaskAttempt | Execution)


class InMemoryDomainStore:
    def __init__(self) -> None:
        self._workspaces: dict[WorkspaceId, Workspace] = {}
        self._goals: dict[GoalId, Goal] = {}
        self._tasks: dict[TaskId, Task] = {}
        self._attempts: dict[TaskAttemptId, TaskAttempt] = {}
        self._executions: dict[ExecutionId, Execution] = {}
        self._events: list[Event] = []
        self._event_ids: set[EventId] = set()
        self._transitions: list[StateTransition] = []
        self._transition_ids: set[StateTransitionId] = set()
        self._lock = RLock()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Rollback canonical state and audit together; no network work inside this scope."""
        with self._lock:
            snapshot = (
                self._workspaces.copy(),
                self._goals.copy(),
                self._tasks.copy(),
                self._attempts.copy(),
                self._executions.copy(),
                self._events.copy(),
                self._event_ids.copy(),
                self._transitions.copy(),
                self._transition_ids.copy(),
            )
            try:
                yield
            except BaseException:
                (
                    self._workspaces,
                    self._goals,
                    self._tasks,
                    self._attempts,
                    self._executions,
                    self._events,
                    self._event_ids,
                    self._transitions,
                    self._transition_ids,
                ) = snapshot
                raise

    @staticmethod
    def _workspace(entity: Workspace | Goal | Task | TaskAttempt | Execution) -> WorkspaceId:
        return entity.id if isinstance(entity, Workspace) else entity.workspace_id

    def _audit_matches(self, entity: TEntity, event: Event) -> None:
        if self._workspace(entity) != event.workspace_id:
            raise WorkspaceMismatch(
                "Event.subject", str(self._workspace(entity)), str(event.workspace_id)
            )
        if (
            event.subject_id != str(entity.id)
            or event.entity_version != entity.version
            or event.subject_type.value != self._subject_type(entity)
        ):
            raise InvariantViolation("event_matches_entity")

    @staticmethod
    def _subject_type(entity: Workspace | Goal | Task | TaskAttempt | Execution) -> str:
        return "task_attempt" if isinstance(entity, TaskAttempt) else type(entity).__name__.lower()

    def _references(self, entity: TEntity) -> None:
        if isinstance(entity, Workspace):
            return
        self.get_workspace(entity.workspace_id)
        parents: list[Goal | Task | Execution] = []
        if isinstance(entity, (Task, Execution)):
            parents.append(self.get_goal(entity.goal_id))
        if isinstance(entity, TaskAttempt):
            task = self.get_task(entity.task_id)
            execution = self.get_execution(entity.execution_id)
            parents.extend((task, execution))
            if task.goal_id != execution.goal_id:
                raise InvariantViolation("attempt_parents_share_goal")
            existing = self.attempts_for_task(task.id)
            if any(item.status not in TaskAttempt.terminal_statuses() for item in existing):
                raise InvariantViolation("one_non_terminal_attempt_per_task")
            if entity.ordinal != len(existing) + 1 or entity.previous_attempt_id != (
                existing[-1].id if existing else None
            ):
                raise InvariantViolation("attempt_lineage")
            if len(self.attempts_for_execution(execution.id)) >= execution.bounds.max_task_attempts:
                raise InvariantViolation("execution_task_attempt_bound")
        for parent in parents:
            if parent.workspace_id != entity.workspace_id:
                raise WorkspaceMismatch(
                    "parent", str(entity.workspace_id), str(parent.workspace_id)
                )

    def _add(
        self,
        entities: dict[TId, TEntity],
        entity_id: TId,
        entity_type: str,
        entity: TEntity,
        event: Event,
    ) -> None:
        with self._lock:
            if entity_id in entities:
                raise InvariantViolation(
                    "entity_id_unique",
                    details={"entity_type": entity_type, "entity_id": str(entity_id)},
                )
            self._validate_event(event)
            self._audit_matches(entity, event)
            self._references(entity)
            if entity.version != Version.initial():
                raise InvariantViolation("creation_requires_initial_version")
            entities[entity_id] = entity
            self._append_event(event)

    def _get(self, entities: dict[TId, TEntity], entity_id: TId, entity_type: str) -> TEntity:
        with self._lock:
            try:
                return entities[entity_id]
            except KeyError as error:
                raise EntityNotFound(entity_type, str(entity_id)) from error

    def _save(
        self,
        entities: dict[TId, TEntity],
        entity_id: TId,
        entity_type: str,
        entity: TEntity,
        expected_version: Version,
        transition: StateTransition,
        event: Event,
    ) -> None:
        with self._lock:
            current = self._get(entities, entity_id, entity_type)
            actual = current.version
            if actual != expected_version:
                raise VersionConflict(
                    entity_type, str(entity_id), expected_version.value, actual.value
                )
            new_version = entity.version
            if new_version != expected_version.next():
                raise InvariantViolation("save_requires_one_version_increment")
            if transition.subject_id != str(entity_id):
                raise InvariantViolation("transition_subject_matches_entity")
            if transition.from_version != expected_version or transition.to_version != new_version:
                raise InvariantViolation("transition_versions_match_entity")
            if event.subject_id != str(entity_id) or event.entity_version != new_version:
                raise InvariantViolation("event_subject_and_version_match_entity")
            self._validate_transition(transition)
            self._validate_event(event)
            self._audit_matches(entity, event)
            if isinstance(current, Workspace) or isinstance(entity, Workspace):
                raise InvariantViolation("workspace_mutation_not_supported")
            allowed = {
                status.value: {target.value for target in targets}
                for status, targets in current._ALLOWED.items()
            }
            if entity.status.value not in allowed[current.status.value]:
                raise InvariantViolation("persisted_transition_must_be_legal")
            mutable = {
                "status",
                "version",
                "updated_at",
                "started_at",
                "ended_at",
                "failure_reason",
            }
            if any(
                getattr(current, field.name) != getattr(entity, field.name)
                for field in fields(current)
                if field.name not in mutable
            ):
                raise InvariantViolation("historical_definition_is_immutable")
            if (
                transition.workspace_id != entity.workspace_id
                or transition.subject_type != event.subject_type
                or transition.previous_status != current.status.value
                or transition.new_status != entity.status.value
                or transition.occurred_at != entity.updated_at
            ):
                raise InvariantViolation("transition_matches_entity")
            entities[entity_id] = entity
            self._transitions.append(transition)
            self._transition_ids.add(transition.id)
            self._append_event(event)

    def _validate_event(self, event: Event) -> None:
        if event.id in self._event_ids:
            raise InvariantViolation("event_id_unique")

    def _append_event(self, event: Event) -> None:
        self._events.append(event)
        self._event_ids.add(event.id)

    def _validate_transition(self, transition: StateTransition) -> None:
        if transition.id in self._transition_ids:
            raise InvariantViolation("state_transition_id_unique")

    def add_workspace(self, workspace: Workspace, event: Event) -> None:
        self._add(self._workspaces, workspace.id, "Workspace", workspace, event)

    def add_goal(self, goal: Goal, event: Event) -> None:
        self._add(self._goals, goal.id, "Goal", goal, event)

    def add_task(self, task: Task, event: Event) -> None:
        self._add(self._tasks, task.id, "Task", task, event)

    def add_task_attempt(self, attempt: TaskAttempt, event: Event) -> None:
        self._add(self._attempts, attempt.id, "TaskAttempt", attempt, event)

    def add_execution(self, execution: Execution, event: Event) -> None:
        self._add(self._executions, execution.id, "Execution", execution, event)

    def get_workspace(self, entity_id: WorkspaceId) -> Workspace:
        return self._get(self._workspaces, entity_id, "Workspace")

    def get_goal(self, entity_id: GoalId) -> Goal:
        return self._get(self._goals, entity_id, "Goal")

    def get_task(self, entity_id: TaskId) -> Task:
        return self._get(self._tasks, entity_id, "Task")

    def get_task_attempt(self, entity_id: TaskAttemptId) -> TaskAttempt:
        return self._get(self._attempts, entity_id, "TaskAttempt")

    def get_execution(self, entity_id: ExecutionId) -> Execution:
        return self._get(self._executions, entity_id, "Execution")

    def save_goal(
        self, goal: Goal, expected_version: Version, transition: StateTransition, event: Event
    ) -> None:
        self._save(self._goals, goal.id, "Goal", goal, expected_version, transition, event)

    def save_task(
        self, task: Task, expected_version: Version, transition: StateTransition, event: Event
    ) -> None:
        self._save(self._tasks, task.id, "Task", task, expected_version, transition, event)

    def save_task_attempt(
        self,
        attempt: TaskAttempt,
        expected_version: Version,
        transition: StateTransition,
        event: Event,
    ) -> None:
        self._save(
            self._attempts,
            attempt.id,
            "TaskAttempt",
            attempt,
            expected_version,
            transition,
            event,
        )

    def save_execution(
        self,
        execution: Execution,
        expected_version: Version,
        transition: StateTransition,
        event: Event,
    ) -> None:
        self._save(
            self._executions,
            execution.id,
            "Execution",
            execution,
            expected_version,
            transition,
            event,
        )

    def tasks_for_goal(self, goal_id: GoalId) -> tuple[Task, ...]:
        with self._lock:
            return tuple(task for task in self._tasks.values() if task.goal_id == goal_id)

    def attempts_for_task(self, task_id: TaskId) -> tuple[TaskAttempt, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (attempt for attempt in self._attempts.values() if attempt.task_id == task_id),
                    key=lambda item: item.ordinal,
                )
            )

    def attempts_for_execution(self, execution_id: ExecutionId) -> tuple[TaskAttempt, ...]:
        with self._lock:
            return tuple(
                attempt
                for attempt in self._attempts.values()
                if attempt.execution_id == execution_id
            )

    def events(self, workspace_id: WorkspaceId | None = None) -> tuple[Event, ...]:
        with self._lock:
            return tuple(
                event
                for event in self._events
                if workspace_id is None or event.workspace_id == workspace_id
            )

    def transitions(self, workspace_id: WorkspaceId | None = None) -> tuple[StateTransition, ...]:
        with self._lock:
            return tuple(
                transition
                for transition in self._transitions
                if workspace_id is None or transition.workspace_id == workspace_id
            )
