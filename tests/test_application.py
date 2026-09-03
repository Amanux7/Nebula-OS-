from collections.abc import Callable
from datetime import timedelta

import pytest

from agent_company_os.adapters.clocks import FakeClock
from agent_company_os.adapters.in_memory import InMemoryDomainStore
from agent_company_os.application.service import (
    CreateExecutionCommand,
    CreateGoalCommand,
    CreateTaskAttemptCommand,
    CreateTaskCommand,
    DomainService,
)
from agent_company_os.domain.errors import (
    InvalidStateTransition,
    InvariantViolation,
    VersionConflict,
    WorkspaceMismatch,
)
from agent_company_os.domain.events import EventType
from agent_company_os.domain.execution import Execution, ExecutionStatus
from agent_company_os.domain.goal import Goal, GoalStatus
from agent_company_os.domain.ids import GoalId, Version, WorkspaceId
from agent_company_os.domain.task import TaskStatus
from agent_company_os.domain.task_attempt import TaskAttemptStatus


def active_goal(service: DomainService, workspace_id: WorkspaceId) -> Goal:
    goal = service.create_goal(
        CreateGoalCommand(workspace_id, "Produce brief", ("Evidence included",))
    )
    return service.activate_goal(goal.id, goal.version)


def running_execution(
    service: DomainService, workspace_id: WorkspaceId, goal_id: GoalId
) -> Execution:
    execution = service.create_execution(
        CreateExecutionCommand(workspace_id, goal_id, "test-user", 4)
    )
    return service.start_execution(execution.id, execution.version)


def test_deterministic_end_to_end_scenario(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
    tick: Callable[[], None],
) -> None:
    workspace = service.create_workspace("Demo")
    tick()
    goal = active_goal(service, workspace.id)
    tasks = [
        service.create_task(CreateTaskCommand(workspace.id, goal.id, title, (criterion,)))
        for title, criterion in (
            ("Research competitors", "Sources recorded"),
            ("Analyze findings", "Findings synthesized"),
        )
    ]
    execution = running_execution(service, workspace.id, goal.id)

    completed_tasks = []
    for task in tasks:
        clock.advance(timedelta(seconds=1))
        task = service.ready_task(task.id, task.version)
        task = service.start_task(task.id, task.version)
        attempt = service.create_task_attempt(
            CreateTaskAttemptCommand(workspace.id, task.id, execution.id)
        )
        attempt = service.start_task_attempt(attempt.id, attempt.version)
        attempt = service.succeed_task_attempt(attempt.id, attempt.version)
        completed_tasks.append(service.complete_task(task.id, attempt.id, task.version))

    execution = service.succeed_execution(execution.id, execution.version)
    goal = service.satisfy_goal(goal.id, goal.version)

    assert all(task.status is TaskStatus.COMPLETED for task in completed_tasks)
    assert execution.status is ExecutionStatus.SUCCEEDED
    assert goal.status is GoalStatus.SATISFIED
    # Seven creation records plus fourteen lifecycle transitions.
    assert len(store.events(workspace.id)) == 21
    assert len(store.transitions(workspace.id)) == 14
    assert [event.event_type for event in store.events(workspace.id)][-2:] == [
        EventType.EXECUTION_SUCCEEDED,
        EventType.GOAL_SATISFIED,
    ]


def test_cross_workspace_task_reference_is_rejected(service: DomainService) -> None:
    workspace_a = service.create_workspace("A")
    workspace_b = service.create_workspace("B")
    goal_a = active_goal(service, workspace_a.id)
    with pytest.raises(WorkspaceMismatch):
        service.create_task(CreateTaskCommand(workspace_b.id, goal_a.id, "Intruder task", ("No",)))


def test_cross_workspace_execution_reference_is_rejected(service: DomainService) -> None:
    workspace_a = service.create_workspace("A")
    workspace_b = service.create_workspace("B")
    goal_a = active_goal(service, workspace_a.id)
    with pytest.raises(WorkspaceMismatch):
        service.create_execution(CreateExecutionCommand(workspace_b.id, goal_a.id, "user", 1))


def test_cross_workspace_attempt_reference_is_rejected(service: DomainService) -> None:
    workspace_a = service.create_workspace("A")
    workspace_b = service.create_workspace("B")
    goal_a = active_goal(service, workspace_a.id)
    task = service.create_task(CreateTaskCommand(workspace_a.id, goal_a.id, "Task", ("Done",)))
    task = service.ready_task(task.id, task.version)
    task = service.start_task(task.id, task.version)
    execution = running_execution(service, workspace_a.id, goal_a.id)
    with pytest.raises(WorkspaceMismatch):
        service.create_task_attempt(CreateTaskAttemptCommand(workspace_b.id, task.id, execution.id))


def test_stale_version_is_rejected(service: DomainService) -> None:
    workspace = service.create_workspace("A")
    goal = active_goal(service, workspace.id)
    with pytest.raises(VersionConflict) as captured:
        service.cancel_goal(goal.id, Version.initial())
    assert captured.value.details["actual_version"] == "2"


def test_attempt_retry_preserves_failed_history(
    service: DomainService, store: InMemoryDomainStore
) -> None:
    workspace = service.create_workspace("A")
    goal = active_goal(service, workspace.id)
    task = service.create_task(CreateTaskCommand(workspace.id, goal.id, "Task", ("Done",)))
    task = service.ready_task(task.id, task.version)
    task = service.start_task(task.id, task.version)
    execution = running_execution(service, workspace.id, goal.id)
    first = service.create_task_attempt(
        CreateTaskAttemptCommand(workspace.id, task.id, execution.id)
    )
    first = service.start_task_attempt(first.id, first.version)
    first = service.fail_task_attempt(first.id, first.version, "provider_timeout")
    task = service.ready_task(task.id, task.version)
    task = service.start_task(task.id, task.version)
    second = service.create_task_attempt(
        CreateTaskAttemptCommand(workspace.id, task.id, execution.id)
    )
    history = store.attempts_for_task(task.id)
    assert history == (first, second)
    assert first.status is TaskAttemptStatus.FAILED
    assert second.previous_attempt_id == first.id
    assert second.ordinal == 2


def test_only_one_non_terminal_attempt_per_task(service: DomainService) -> None:
    workspace = service.create_workspace("A")
    goal = active_goal(service, workspace.id)
    task = service.create_task(CreateTaskCommand(workspace.id, goal.id, "Task", ("Done",)))
    task = service.ready_task(task.id, task.version)
    task = service.start_task(task.id, task.version)
    execution = running_execution(service, workspace.id, goal.id)
    command = CreateTaskAttemptCommand(workspace.id, task.id, execution.id)
    service.create_task_attempt(command)
    with pytest.raises(InvariantViolation):
        service.create_task_attempt(command)


def test_duplicate_goal_completion_does_not_append_audit(
    service: DomainService, store: InMemoryDomainStore
) -> None:
    workspace = service.create_workspace("A")
    goal = active_goal(service, workspace.id)
    task = service.create_task(CreateTaskCommand(workspace.id, goal.id, "Task", ("Done",)))
    task = service.ready_task(task.id, task.version)
    task = service.start_task(task.id, task.version)
    execution = running_execution(service, workspace.id, goal.id)
    attempt = service.create_task_attempt(
        CreateTaskAttemptCommand(workspace.id, task.id, execution.id)
    )
    attempt = service.start_task_attempt(attempt.id, attempt.version)
    attempt = service.succeed_task_attempt(attempt.id, attempt.version)
    service.complete_task(task.id, attempt.id, task.version)
    goal = service.satisfy_goal(goal.id, goal.version)
    before = len(store.events())
    with pytest.raises(InvalidStateTransition):
        service.satisfy_goal(goal.id, goal.version)
    assert len(store.events()) == before
