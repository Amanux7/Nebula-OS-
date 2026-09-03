import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path

import pytest

from agent_company_os.adapters.clocks import FakeClock
from agent_company_os.adapters.fake_model import FakeModel
from agent_company_os.adapters.in_memory import InMemoryDomainStore
from agent_company_os.adapters.runtime_store import InMemoryRuntimeStore
from agent_company_os.application.research_agent import research_brief_agent
from agent_company_os.application.runtime import AgentRuntimeService
from agent_company_os.application.runtime_serialization import serialize_run
from agent_company_os.application.service import (
    CreateExecutionCommand,
    CreateGoalCommand,
    CreateTaskAttemptCommand,
    CreateTaskCommand,
    DomainService,
)
from agent_company_os.domain.agent import (
    ActionType,
    AgentDefinitionId,
    AgentRun,
    AgentRunStatus,
    Fact,
    RuntimeLimits,
    SourceText,
    SuppliedContext,
)
from agent_company_os.domain.decisions import ModelFailure
from agent_company_os.domain.errors import InvariantViolation, VersionConflict, WorkspaceMismatch
from agent_company_os.domain.events import EventType
from agent_company_os.domain.execution import ExecutionStatus
from agent_company_os.domain.goal import GoalStatus
from agent_company_os.domain.ids import Version
from agent_company_os.domain.task import TaskStatus
from agent_company_os.domain.task_attempt import TaskAttemptStatus
from agent_company_os.domain.transitions import StateTransition
from agent_company_os.ports.model import AgentModelRequest


def decision(action: str, payload: object) -> str:
    return json.dumps({"schema_version": 1, "action_type": action, "payload": payload})


def completion(context: SuppliedContext, gaps: tuple[str, ...] = ()) -> str:
    return decision(
        "complete_task",
        {
            "findings": [
                {"key": fact.key, "value": fact.value, "source_id": fact.source_id}
                for fact in context.facts
                if fact.key in context.required_keys and fact.key not in gaps
            ],
            "gaps": list(gaps),
        },
    )


@dataclass
class Harness:
    runtime: AgentRuntimeService
    store: InMemoryRuntimeStore
    run: AgentRun
    model: FakeModel

    def drive(self) -> AgentRun:
        self.run = asyncio.run(
            self.runtime.drive(self.run.workspace_id, self.run.id, self.run.version)
        )
        return self.run


def setup(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
    case: str = "complete_context",
    responses: tuple[str | Exception, ...] | None = None,
    limits: RuntimeLimits | None = None,
    on_invoke: Callable[[AgentModelRequest], None] | None = None,
) -> Harness:
    workspace = service.create_workspace("Research")
    goal = service.create_goal(CreateGoalCommand(workspace.id, "Prepare brief", ("Grounded",)))
    goal = service.activate_goal(goal.id, goal.version)
    task = service.create_task(
        CreateTaskCommand(workspace.id, goal.id, "Compare facts", ("No invented facts",))
    )
    task = service.ready_task(task.id, task.version)
    task = service.start_task(task.id, task.version)
    execution = service.create_execution(
        CreateExecutionCommand(workspace.id, goal.id, "test-user", 5)
    )
    execution = service.start_execution(execution.id, execution.version)
    attempt = service.create_task_attempt(
        CreateTaskAttemptCommand(workspace.id, task.id, execution.id)
    )
    attempt = service.start_task_attempt(attempt.id, attempt.version)
    cases = json.loads((Path(__file__).parent / "fixtures/agent_eval/cases.json").read_text())
    data = cases[case]
    context = SuppliedContext(
        workspace.id,
        task.id,
        tuple(data["required_keys"]),
        tuple(Fact(**fact) for fact in data["facts"]),
        tuple(SourceText(**source) for source in data["source_texts"]),
    )
    model = FakeModel(
        responses
        if responses is not None
        else (completion(context, tuple(data["expected_gaps"])),),
        on_invoke,
    )
    runtime_store = InMemoryRuntimeStore(store)
    definition = research_brief_agent(workspace.id, AgentDefinitionId(str(service.ids.event_id())))
    runtime_store.publish(definition)
    runtime = AgentRuntimeService(runtime_store, clock, service.ids, model)
    run = runtime.start(
        workspace.id, definition.definition.id, definition.version, attempt.id, context, limits
    )
    return Harness(runtime, runtime_store, run, model)


@pytest.mark.parametrize(
    "case",
    [
        "complete_context",
        "missing_fact",
        "conflicting_fact",
        "irrelevant_context",
        "instruction_attack",
    ],
)
def test_grounded_completion_fixtures(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
    case: str,
) -> None:
    harness = setup(service, store, clock, case)
    run = harness.drive()
    assert run.status is AgentRunStatus.SUCCEEDED
    assert run.result is not None
    assert all(fact in run.context.facts for fact in run.result.findings)
    assert store.get_task(run.task_id).status is TaskStatus.COMPLETED
    assert store.get_task_attempt(run.task_attempt_id).status is TaskAttemptStatus.SUCCEEDED
    assert store.get_execution(run.execution_id).status is ExecutionStatus.SUCCEEDED
    assert (
        store.get_goal(run.goal_id).status is GoalStatus.ACTIVE
    )  # explicit acceptance remains human/application
    assert len(harness.store.actions(run.workspace_id)) == 1
    assert harness.store.transitions(run.workspace_id)[-1].new_status == "succeeded"


def test_multi_iteration_and_bounded_context(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(service, store, clock, limits=RuntimeLimits(recent_observations=1))
    harness.runtime.model = FakeModel(
        (decision("respond", {"message": "Intermediate draft"}), completion(harness.run.context))
    )
    run = harness.drive()
    assert run.status is AgentRunStatus.SUCCEEDED
    assert run.working_state.iteration == 2
    assert len(run.working_state.observations) == 1


def test_wait_supply_resume_same_identity(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(
        service,
        store,
        clock,
        "missing_fact",
        responses=(decision("request_more_context", {"missing_fields": ["B.price"]}),),
    )
    run = harness.drive()
    assert run.status is AgentRunStatus.WAITING
    assert store.get_execution(run.execution_id).status is ExecutionStatus.WAITING
    assert store.get_task_attempt(run.task_attempt_id).status is TaskAttemptStatus.RUNNING
    context = replace(
        run.context, facts=(*run.context.facts, Fact("B.price", "200/month", "source_2"))
    )
    harness.run = harness.runtime.resume(run.workspace_id, run.id, run.version, context)
    harness.runtime.model = FakeModel((completion(context),))
    finished = harness.drive()
    assert finished.id == run.id
    assert finished.task_attempt_id == run.task_attempt_id
    assert finished.working_state.iteration == 2
    assert finished.status is AgentRunStatus.SUCCEEDED


@pytest.mark.parametrize(
    ("response", "code"),
    [
        ("not json", "malformed_output"),
        ("", "empty_response"),
        (
            '{"schema_version": true, "action_type":"respond", "payload":{}}',
            "unsupported_schema_version",
        ),
        (decision("delete_database", {}), "unauthorized_action"),
        (decision("complete_task", {}), "schema_violation"),
        (decision("respond", {"message": "draft", "permissions": "admin"}), "schema_violation"),
        (TimeoutError(), "model_timeout"),
        (ModelFailure("rate_limited"), "rate_limited"),
        (RuntimeError("secret-provider-credential"), "provider_unavailable"),
    ],
)
def test_model_failures_do_not_fail_business_task(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
    response: str | Exception,
    code: str,
) -> None:
    harness = setup(service, store, clock, responses=(response,))
    run = harness.drive()
    assert run.status is AgentRunStatus.FAILED
    assert run.error_code == code
    assert store.get_task(run.task_id).status is TaskStatus.READY
    assert store.get_goal(run.goal_id).status is GoalStatus.ACTIVE
    assert "secret-provider-credential" not in repr(harness.store.events(run.workspace_id))


def test_hallucinated_fact_rejected(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(service, store, clock, "instruction_attack")
    invented = replace(
        harness.run.context,
        facts=(*harness.run.context.facts, Fact("B.price", "499/month", "hostile_source")),
    )
    harness.runtime.model = FakeModel((completion(invented),))
    assert harness.drive().error_code == "unsupported_completion"


def test_unsupported_completion_fixture(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(service, store, clock, "unsupported_completion")
    assert harness.drive().status is AgentRunStatus.FAILED


def test_iteration_limit_stops_loop(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(
        service,
        store,
        clock,
        responses=(decision("respond", {"message": "more"}),) * 3,
        limits=RuntimeLimits(max_iterations=3),
    )
    assert harness.drive().error_code == "iteration_limit_exceeded"
    assert len(harness.model.requests) == 3


def test_deadline_checked_after_model(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(service, store, clock, on_invoke=lambda _: clock.advance(timedelta(seconds=61)))
    assert harness.drive().error_code == "deadline_exceeded"


def test_wait_does_not_reset_deadline(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(
        service,
        store,
        clock,
        "missing_fact",
        responses=(decision("request_more_context", {"missing_fields": ["B.price"]}),),
    )
    run = harness.drive()
    clock.advance(timedelta(seconds=61))
    expired = harness.runtime.resume(run.workspace_id, run.id, run.version, run.context)
    assert expired.error_code == "deadline_exceeded"


def test_stale_parent_model_decision_rejected(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(service, store, clock)
    task = store.get_task(harness.run.task_id)

    def stale_update(_: AgentModelRequest) -> None:
        service.ready_task(task.id, task.version)

    harness.runtime.model = FakeModel((completion(harness.run.context),), stale_update)
    run = harness.drive()
    assert run.status is AgentRunStatus.FAILED
    assert run.error_code == "version_conflict"
    assert store.get_task(task.id).status is TaskStatus.READY
    assert run.result is None


def test_cross_workspace_and_duplicate_starts(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(service, store, clock)
    run = harness.run
    definition = run.definition_version
    other = service.create_workspace("Other")
    with pytest.raises(WorkspaceMismatch):
        harness.runtime.start(
            other.id, definition.definition.id, definition.version, run.task_attempt_id, run.context
        )
    with pytest.raises(InvariantViolation):
        harness.runtime.start(
            run.workspace_id,
            definition.definition.id,
            definition.version,
            run.task_attempt_id,
            run.context,
        )
    with pytest.raises(WorkspaceMismatch):
        harness.store.get_run(other.id, run.id)


def test_historical_configuration_and_terminal_identity(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(service, store, clock)
    original = harness.run.definition_version
    run = harness.drive()
    harness.store.publish(replace(original, version=Version(2), instructions="New instructions"))
    assert harness.store.get_run(run.workspace_id, run.id).definition_version == original
    with pytest.raises(InvariantViolation):
        harness.store.publish(original)
    with pytest.raises(InvariantViolation):
        harness.drive()


def test_stale_run_command_rejected(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(service, store, clock)
    run = harness.drive()
    with pytest.raises(VersionConflict):
        asyncio.run(harness.runtime.drive(run.workspace_id, run.id, Version(1)))


def test_definition_policy_cannot_be_widened_by_model(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(service, store, clock)
    narrowed = replace(
        harness.run.definition_version, version=Version(2), allowed_actions=(ActionType.RESPOND,)
    )
    # Test policy directly against the exact immutable effective snapshot.
    from agent_company_os.application.context import ActionPolicy
    from agent_company_os.domain.decisions import parse_decision

    with pytest.raises(ModelFailure, match="unauthorized_action"):
        ActionPolicy().authorize(
            replace(harness.run, definition_version=narrowed),
            parse_decision(completion(harness.run.context), 8000),
        )


def test_context_and_response_bounds(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(service, store, clock, limits=RuntimeLimits(max_context_chars=10))
    assert harness.drive().error_code == "context_overflow"
    assert harness.model.requests == []
    second = setup(service, store, clock, responses=("x" * 8001,))
    assert second.drive().error_code == "response_too_large"


def test_cancellation_while_model_in_flight(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(service, store, clock)

    async def scenario() -> AgentRun:
        entered = asyncio.Event()
        release = asyncio.Event()

        class BlockingModel:
            model_name = "scripted-v1"

            async def invoke(self, request: AgentModelRequest) -> str:
                entered.set()
                await release.wait()
                return completion(request.supplied_data)

        harness.runtime.model = BlockingModel()
        run = harness.run
        pending = asyncio.create_task(harness.runtime.drive(run.workspace_id, run.id, run.version))
        await entered.wait()
        current = harness.store.get_run(run.workspace_id, run.id)
        with pytest.raises(InvariantViolation):
            await harness.runtime.drive(run.workspace_id, run.id, current.version)
        harness.runtime.cancel(run.workspace_id, run.id, current.version)
        release.set()
        return await pending

    result = asyncio.run(scenario())
    assert result.status is AgentRunStatus.CANCELLED
    assert store.get_task_attempt(result.task_attempt_id).status is TaskAttemptStatus.CANCELLED


def test_real_async_invocation_timeout(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(service, store, clock, limits=RuntimeLimits(model_seconds=1))

    class HangingModel:
        model_name = "scripted-v1"

        async def invoke(self, request: AgentModelRequest) -> str:
            await asyncio.Event().wait()
            return "unreachable"

    harness.runtime.model = HangingModel()
    assert harness.drive().error_code == "model_timeout"


def test_runtime_audit_is_correlated(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(service, store, clock)
    run = harness.drive()
    events = harness.store.events(run.workspace_id)
    assert EventType.AGENT_RUN_COMPLETED in [event.event_type for event in events]
    assert all(dict(event.metadata)["agent_run_id"] == str(run.id) for event in events)
    assert all(dict(event.metadata)["agent_definition_version"] == "1" for event in events)


def test_multi_record_completion_rolls_back_on_storage_failure(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = setup(service, store, clock)
    original = harness.store.save_run

    def fail_after_save(
        run: AgentRun,
        expected_version: Version,
        transition: StateTransition | None,
    ) -> None:
        original(run, expected_version, transition)
        if run.status is AgentRunStatus.SUCCEEDED:
            raise RuntimeError("injected commit failure")

    monkeypatch.setattr(harness.store, "save_run", fail_after_save)
    run = harness.drive()
    assert run.error_code == "runtime_error"
    assert store.get_task(run.task_id).status is TaskStatus.READY
    assert store.get_task_attempt(run.task_attempt_id).status is TaskAttemptStatus.FAILED
    assert harness.store.actions(run.workspace_id) == ()
    assert all(event.event_type is not EventType.TASK_COMPLETED for event in store.events())
    assert all(
        event.event_type is not EventType.AGENT_RUN_COMPLETED
        for event in harness.store.events(run.workspace_id)
    )


def test_fake_citation_cannot_support_changed_fact(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(service, store, clock)
    forged = replace(
        harness.run.context,
        facts=(
            Fact("A.price", "999/month", "source_1"),
            harness.run.context.facts[1],
        ),
    )
    harness.runtime.model = FakeModel((completion(forged),))
    assert harness.drive().error_code == "ungrounded_fact"


def test_response_cannot_resolve_conflicting_evidence_arbitrarily(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(service, store, clock, "conflicting_fact")
    forged = replace(harness.run.context, facts=harness.run.context.facts[:2])
    harness.runtime.model = FakeModel((completion(forged),))
    assert harness.drive().error_code == "unsupported_completion"


def test_run_serialization_is_json_safe_and_versioned(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(service, store, clock)
    run = harness.drive()
    serialized = serialize_run(run)
    assert json.loads(json.dumps(serialized)) == serialized
    assert serialized["schema_version"] == 1
    assert serialized["agent_definition_version"] == 1
    assert serialized["status"] == "succeeded"
    assert "instructions" not in serialized


def test_wait_resume_keeps_iteration_budget(
    service: DomainService,
    store: InMemoryDomainStore,
    clock: FakeClock,
) -> None:
    harness = setup(
        service,
        store,
        clock,
        "missing_fact",
        responses=(decision("request_more_context", {"missing_fields": ["B.price"]}),),
        limits=RuntimeLimits(max_iterations=1),
    )
    run = harness.drive()
    harness.run = harness.runtime.resume(run.workspace_id, run.id, run.version, run.context)
    assert harness.drive().error_code == "iteration_limit_exceeded"
    assert len(harness.model.requests) == 1


def test_runtime_failure_codes_do_not_accept_arbitrary_provider_text() -> None:
    assert ModelFailure("secret-canary").code == "provider_unavailable"
