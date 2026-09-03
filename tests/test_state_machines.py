from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from agent_company_os.domain.errors import InvalidStateTransition, InvariantViolation
from agent_company_os.domain.execution import Execution, ExecutionBounds, ExecutionStatus
from agent_company_os.domain.goal import Goal, GoalStatus
from agent_company_os.domain.ids import (
    ExecutionId,
    GoalId,
    StateTransitionId,
    TaskAttemptId,
    TaskId,
    WorkspaceId,
)
from agent_company_os.domain.task import Task, TaskStatus
from agent_company_os.domain.task_attempt import TaskAttempt, TaskAttemptStatus
from agent_company_os.domain.transitions import TransitionResult

NOW = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(seconds=1)
WS = WorkspaceId("ws")
GOAL_ID = GoalId("goal")
TASK_ID = TaskId("task")
EXECUTION_ID = ExecutionId("execution")


def goal(status: GoalStatus = GoalStatus.DRAFT) -> Goal:
    return replace(Goal.create(GOAL_ID, WS, "Outcome", (), ("Accepted",), NOW), status=status)


def task(status: TaskStatus = TaskStatus.PROPOSED) -> Task:
    return replace(Task.create(TASK_ID, WS, GOAL_ID, "Work", ("Done",), NOW), status=status)


def attempt(status: TaskAttemptStatus = TaskAttemptStatus.CREATED) -> TaskAttempt:
    return replace(
        TaskAttempt.create(TaskAttemptId("attempt"), WS, TASK_ID, EXECUTION_ID, 1, None, NOW),
        status=status,
        started_at=NOW if status is not TaskAttemptStatus.CREATED else None,
    )


def execution(status: ExecutionStatus = ExecutionStatus.CREATED) -> Execution:
    return replace(
        Execution.create(EXECUTION_ID, WS, GOAL_ID, "user", ExecutionBounds(3), None, NOW),
        status=status,
        started_at=NOW if status is not ExecutionStatus.CREATED else None,
    )


@pytest.mark.parametrize(
    ("source", "operation", "target"),
    [
        (
            GoalStatus.DRAFT,
            lambda item: item.activate(StateTransitionId("t"), LATER),
            GoalStatus.ACTIVE,
        ),
        (
            GoalStatus.DRAFT,
            lambda item: item.cancel(StateTransitionId("t"), LATER),
            GoalStatus.CANCELLED,
        ),
        (
            GoalStatus.ACTIVE,
            lambda item: item.satisfy(StateTransitionId("t"), LATER),
            GoalStatus.SATISFIED,
        ),
        (
            GoalStatus.ACTIVE,
            lambda item: item.close_unsatisfied(StateTransitionId("t"), LATER),
            GoalStatus.CLOSED_UNSATISFIED,
        ),
        (
            GoalStatus.ACTIVE,
            lambda item: item.cancel(StateTransitionId("t"), LATER),
            GoalStatus.CANCELLED,
        ),
    ],
)
def test_all_legal_goal_transitions(
    source: GoalStatus, operation: Callable[[Goal], TransitionResult[Goal]], target: GoalStatus
) -> None:
    result = operation(goal(source))
    assert result.entity.status is target


@pytest.mark.parametrize(
    ("source", "method", "target"),
    [
        (TaskStatus.PROPOSED, "mark_ready", TaskStatus.READY),
        (TaskStatus.PROPOSED, "cancel", TaskStatus.CANCELLED),
        (TaskStatus.READY, "start", TaskStatus.IN_PROGRESS),
        (TaskStatus.READY, "cancel", TaskStatus.CANCELLED),
        (TaskStatus.IN_PROGRESS, "complete", TaskStatus.COMPLETED),
        (TaskStatus.IN_PROGRESS, "mark_ready", TaskStatus.READY),
        (TaskStatus.IN_PROGRESS, "block", TaskStatus.BLOCKED),
        (TaskStatus.IN_PROGRESS, "fail", TaskStatus.FAILED),
        (TaskStatus.IN_PROGRESS, "cancel", TaskStatus.CANCELLED),
        (TaskStatus.BLOCKED, "mark_ready", TaskStatus.READY),
        (TaskStatus.BLOCKED, "fail", TaskStatus.FAILED),
        (TaskStatus.BLOCKED, "cancel", TaskStatus.CANCELLED),
    ],
)
def test_all_legal_task_transitions(source: TaskStatus, method: str, target: TaskStatus) -> None:
    result = getattr(task(source), method)(StateTransitionId("t"), LATER)
    assert result.entity.status is target


@pytest.mark.parametrize(
    ("source", "method", "target"),
    [
        (TaskAttemptStatus.CREATED, "start", TaskAttemptStatus.RUNNING),
        (TaskAttemptStatus.CREATED, "cancel", TaskAttemptStatus.CANCELLED),
        (TaskAttemptStatus.RUNNING, "succeed", TaskAttemptStatus.SUCCEEDED),
        (TaskAttemptStatus.RUNNING, "fail", TaskAttemptStatus.FAILED),
        (TaskAttemptStatus.RUNNING, "cancel", TaskAttemptStatus.CANCELLED),
    ],
)
def test_all_legal_attempt_transitions(
    source: TaskAttemptStatus, method: str, target: TaskAttemptStatus
) -> None:
    args = (
        (StateTransitionId("t"), LATER, "timeout")
        if method == "fail"
        else (
            StateTransitionId("t"),
            LATER,
        )
    )
    result = getattr(attempt(source), method)(*args)
    assert result.entity.status is target


@pytest.mark.parametrize(
    ("source", "method", "target"),
    [
        (ExecutionStatus.CREATED, "start", ExecutionStatus.RUNNING),
        (ExecutionStatus.CREATED, "cancel", ExecutionStatus.CANCELLED),
        (ExecutionStatus.RUNNING, "wait", ExecutionStatus.WAITING),
        (ExecutionStatus.RUNNING, "succeed", ExecutionStatus.SUCCEEDED),
        (ExecutionStatus.RUNNING, "fail", ExecutionStatus.FAILED),
        (ExecutionStatus.RUNNING, "cancel", ExecutionStatus.CANCELLED),
        (ExecutionStatus.WAITING, "resume", ExecutionStatus.RUNNING),
        (ExecutionStatus.WAITING, "fail", ExecutionStatus.FAILED),
        (ExecutionStatus.WAITING, "cancel", ExecutionStatus.CANCELLED),
    ],
)
def test_all_legal_execution_transitions(
    source: ExecutionStatus, method: str, target: ExecutionStatus
) -> None:
    args = (
        (StateTransitionId("t"), LATER, "timed_out")
        if method == "fail"
        else (
            StateTransitionId("t"),
            LATER,
        )
    )
    result = getattr(execution(source), method)(*args)
    assert result.entity.status is target


def test_completed_goal_cannot_reopen() -> None:
    with pytest.raises(InvalidStateTransition):
        goal(GoalStatus.SATISFIED).activate(StateTransitionId("t"), LATER)


def test_pending_task_cannot_complete() -> None:
    with pytest.raises(InvalidStateTransition):
        task().complete(StateTransitionId("t"), LATER)


def test_duplicate_completion_is_explicit_error() -> None:
    with pytest.raises(InvalidStateTransition):
        task(TaskStatus.COMPLETED).complete(StateTransitionId("t"), LATER)


def test_timeout_is_failure_reason_not_status() -> None:
    result = execution(ExecutionStatus.RUNNING).fail(StateTransitionId("t"), LATER, "timed_out")
    assert result.entity.status is ExecutionStatus.FAILED
    assert result.entity.failure_reason == "timed_out"


def test_retry_attempt_requires_history_link() -> None:
    with pytest.raises(InvariantViolation):
        TaskAttempt.create(TaskAttemptId("attempt-2"), WS, TASK_ID, EXECUTION_ID, 2, None, NOW)
