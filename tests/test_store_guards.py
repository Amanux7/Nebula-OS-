from dataclasses import replace

import pytest

from agent_company_os.adapters.in_memory import InMemoryDomainStore
from agent_company_os.application.service import CreateGoalCommand, DomainService
from agent_company_os.domain.errors import InvariantViolation, WorkspaceMismatch
from agent_company_os.domain.events import EventType
from agent_company_os.domain.ids import EventId, GoalId, TaskId, Version, WorkspaceId


def test_ids_are_differentiated() -> None:
    goal_id: object = GoalId("same")
    task_id: object = TaskId("same")
    assert goal_id != task_id
    assert str(GoalId("opaque")) == "opaque"
    with pytest.raises(InvariantViolation):
        Version(0)


def test_cross_workspace_event_rejected(service: DomainService) -> None:
    workspace = service.create_workspace("A")
    event = service.store.events()[-1]
    other = replace(workspace, id=WorkspaceId("other"))
    with pytest.raises(WorkspaceMismatch):
        service.store.add_workspace(other, replace(event, id=EventId("other-event")))


def test_transaction_rolls_back_state_and_audit(
    service: DomainService, store: InMemoryDomainStore
) -> None:
    workspace = service.create_workspace("A")
    before = store.events()
    with pytest.raises(InvariantViolation), store.transaction():
        service.create_goal(CreateGoalCommand(workspace.id, "Outcome", ("Done",)))
        raise InvariantViolation("injected_failure")
    assert store.events() == before


def test_forged_historical_mutation_is_rejected(service: DomainService) -> None:
    workspace = service.create_workspace("A")
    goal = service.create_goal(CreateGoalCommand(workspace.id, "Outcome", ("Done",)))
    result = goal.activate(service.ids.state_transition_id(), service.clock.now())
    event = replace(
        service.store.events()[-1],
        id=EventId("forged-event"),
        event_type=EventType.GOAL_ACTIVATED,
        entity_version=result.entity.version,
    )
    with pytest.raises(InvariantViolation):
        service.store.save_goal(
            replace(result.entity, objective="Rewritten"), goal.version, result.transition, event
        )
    assert service.store.get_goal(goal.id) == goal


def test_duplicate_event_rejects_whole_mutation(service: DomainService) -> None:
    workspace = service.create_workspace("A")
    goal = service.create_goal(CreateGoalCommand(workspace.id, "Outcome", ("Done",)))
    result = goal.activate(service.ids.state_transition_id(), service.clock.now())
    event = replace(service.store.events()[-1], entity_version=result.entity.version)
    with pytest.raises(InvariantViolation):
        service.store.save_goal(result.entity, goal.version, result.transition, event)
    assert service.store.get_goal(goal.id) == goal
    assert service.store.transitions() == ()
