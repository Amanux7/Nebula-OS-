from collections.abc import Callable

from agent_company_os.application.service import CreateGoalCommand, DomainService
from agent_company_os.domain.errors import VersionConflict
from agent_company_os.domain.ids import Version
from agent_company_os.serialization import serialize_entity, serialize_error, serialize_event


def test_entity_and_event_serialization_are_explicit(
    service: DomainService, tick: Callable[[], None]
) -> None:
    workspace = service.create_workspace("Serialization")
    tick()
    goal = service.create_goal(CreateGoalCommand(workspace.id, "Outcome", ("Accepted",)))
    payload = serialize_entity(goal)
    event_payload = serialize_event(service.store.events()[-1])
    assert payload["id"] == "test-goal-0001"
    assert payload["status"] == "draft"
    assert payload["version"] == 1
    assert payload["created_at"] == "2026-08-29T09:00:01+00:00"
    assert event_payload["event_type"] == "goal_created"
    assert event_payload["schema_version"] == 1


def test_structured_error_serialization(service: DomainService) -> None:
    workspace = service.create_workspace("Errors")
    goal = service.create_goal(CreateGoalCommand(workspace.id, "Outcome", ("Accepted",)))
    goal = service.activate_goal(goal.id, goal.version)
    try:
        service.cancel_goal(goal.id, Version.initial())
    except VersionConflict as error:
        payload = serialize_error(error)
    else:
        raise AssertionError("Expected VersionConflict")
    assert payload == {
        "code": "version_conflict",
        "message": ("Version conflict for Goal test-goal-0001: expected 1, actual 2."),
        "details": {
            "entity_type": "Goal",
            "entity_id": "test-goal-0001",
            "expected_version": "1",
            "actual_version": "2",
        },
    }
