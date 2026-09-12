# mypy: disable-error-code="no-untyped-call,no-untyped-def"
"""Offline exact-intent governance and cross-stage adversarial regression tests."""

import asyncio
import json
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from agent_company_os.adapters.fake_model import FakeModel
from agent_company_os.adapters.fixture_message import FixtureMessageExecutor
from agent_company_os.adapters.runtime_store import InMemoryRuntimeStore
from agent_company_os.adapters.tool_executors import FakeToolExecutor, output_json
from agent_company_os.adapters.tool_registry import ToolRegistry
from agent_company_os.application.governance import GovernanceService
from agent_company_os.application.governance_serialization import (
    governance_metrics,
    serialize_governed_action,
)
from agent_company_os.application.research_agent import research_brief_agent
from agent_company_os.application.runtime import AgentRuntimeService
from agent_company_os.application.service import (
    CreateExecutionCommand,
    CreateGoalCommand,
    CreateTaskAttemptCommand,
    CreateTaskCommand,
)
from agent_company_os.application.tool_runtime import ToolRuntimeService
from agent_company_os.application.tool_validation import input_json, validate_input
from agent_company_os.domain.agent import (
    ActionType,
    AgentDefinitionId,
    AgentRunId,
    Fact,
    SuppliedContext,
)
from agent_company_os.domain.errors import InvariantViolation, WorkspaceMismatch
from agent_company_os.domain.events import EventType
from agent_company_os.domain.governance import (
    ApprovalEffect,
    ApprovalPolicy,
    DecisionKind,
    ReviewerId,
    ReviewerPrincipal,
    fingerprint,
)
from agent_company_os.domain.ids import Version
from agent_company_os.domain.tools import (
    ExecutorKind,
    FixtureMessageInput,
    ToolDefinition,
    ToolId,
    ToolOutput,
    ToolRisk,
    ToolVersion,
)
from test_tools import call, complete


class GovernanceHarness:
    def __init__(
        self,
        domain,
        clock,
        *,
        autonomy=2,
        grant=True,
        bounded=False,
        risk=ToolRisk.EXTERNAL_WRITE,
        executor=None,
        responses=None,
    ):
        self.domain, self.clock = domain, clock
        self.workspace = domain.create_workspace("Approval fixture company")
        self.goal = domain.create_goal(
            CreateGoalCommand(self.workspace.id, "Prepare and deliver brief", ("Exact evidence",))
        )
        self.goal = domain.activate_goal(self.goal.id, self.goal.version)
        task = domain.create_task(
            CreateTaskCommand(
                self.workspace.id, self.goal.id, "Deliver fixture brief", ("Receipt",)
            )
        )
        task = domain.ready_task(task.id, task.version)
        self.task = domain.start_task(task.id, task.version)
        execution = domain.create_execution(
            CreateExecutionCommand(self.workspace.id, self.goal.id, "host", 5)
        )
        self.execution = domain.start_execution(execution.id, execution.version)
        attempt = domain.create_task_attempt(
            CreateTaskAttemptCommand(self.workspace.id, task.id, execution.id)
        )
        self.attempt = domain.start_task_attempt(attempt.id, attempt.version)
        self.store = InMemoryRuntimeStore(domain.store)
        self.registry = ToolRegistry()
        self.tool = ToolVersion(
            ToolDefinition(
                ToolId(str(domain.ids.event_id())),
                self.workspace.id,
                "Fixture message",
                "Offline message delivery",
                risk,
            ),
            Version(1),
            ExecutorKind.SEND_FIXTURE_MESSAGE,
            "send_fixture_message.v1",
        )
        self.executor = executor or FixtureMessageExecutor()
        self.registry.publish(self.tool, self.executor)
        self.definition = replace(
            research_brief_agent(self.workspace.id, AgentDefinitionId(str(domain.ids.event_id()))),
            allowed_actions=tuple(ActionType),
            autonomy_ceiling=autonomy,
            allowed_tools=(self.tool.grant,) if grant else (),
        )
        self.store.publish(self.definition)
        self.reviewer = ReviewerPrincipal(ReviewerId("human-reviewer-1"), self.workspace.id)
        self.policy = ApprovalPolicy(
            self.workspace.id,
            Version(1),
            (self.tool.grant,),
            ("customer:paper-kite",),
            (self.reviewer,),
            bounded_execute=bounded,
        )
        self.store.publish_approval_policy(self.policy)
        self.governance = GovernanceService(self.store, clock, domain.ids)
        self.tools = ToolRuntimeService(
            self.store, self.registry, clock, domain.ids, self.governance
        )
        self.model = FakeModel(responses or (self.proposal(), complete("approved_001")))
        self.runtime = AgentRuntimeService(self.store, clock, domain.ids, self.model, self.tools)
        self.run = self.runtime.start(
            self.workspace.id,
            self.definition.definition.id,
            Version(1),
            self.attempt.id,
            SuppliedContext(
                self.workspace.id,
                task.id,
                ("pricing",),
                (Fact("pricing", "$49/month", "approved_001"),),
            ),
        )

    def proposal(self, **changes):
        return call(
            str(self.tool.definition.id),
            {
                "destination": "customer:paper-kite",
                "message": "Your requested brief is ready.",
                **changes,
            },
        )

    def drive(self):
        self.run = asyncio.run(self.runtime.drive(self.workspace.id, self.run.id, self.run.version))
        return self.run

    def record(self):
        return self.store.governed_actions(self.workspace.id)[0]

    def review(self, kind=DecisionKind.APPROVED):
        r = self.record()
        return self.governance.decide(
            self.workspace.id, r.intent.id, r.intent.fingerprint, self.reviewer, kind
        )

    def resume(self):
        self.run = asyncio.run(
            self.runtime.resume_approval(
                self.workspace.id, self.run.id, self.record().intent.id, self.run.version
            )
        )
        return self.run

    def receipts(self):
        return self.store.tool_receipts(self.workspace.id, self.run.id)


def test_level2_exact_approval_wait_resume_demo(service, clock):
    h = GovernanceHarness(service, clock)
    original = h.run
    assert h.drive().status == "waiting"
    assert not h.executor.deliveries
    record = h.record()
    assert record.request is not None and record.intent.effect is ApprovalEffect.REQUIRED
    assert h.run.working_state.iteration == 1
    clock.advance(timedelta(seconds=1))
    h.review()
    assert h.resume().status == "succeeded"
    assert h.run.id == original.id and h.run.deadline == original.deadline
    assert h.run.task_attempt_id == original.task_attempt_id
    assert h.run.working_state.iteration == 2
    assert len(h.executor.deliveries) == 1 and len(h.receipts()) == 1
    assert h.record().consumed
    goal = service.store.get_goal(h.goal.id)
    assert service.satisfy_goal(goal.id, goal.version).status == "satisfied"
    exported = serialize_governed_action(h.record(), h.receipts())
    assert exported["outcome"] == "observed_success"
    assert json.loads(json.dumps(exported))["fingerprint"] == record.intent.fingerprint
    kinds = {e.event_type for e in h.store.events(h.workspace.id)}
    assert {
        EventType.ACTION_INTENT_CREATED,
        EventType.APPROVAL_REQUESTED,
        EventType.APPROVAL_GRANTED,
        EventType.ACTION_EXECUTION_AUTHORIZED,
        EventType.APPROVAL_CONSUMED,
        EventType.TOOL_RECEIPT_RECORDED,
    } <= kinds
    metrics = governance_metrics(
        h.store.governed_actions(h.workspace.id), h.store.events(h.workspace.id)
    )
    assert metrics["approval_rate"] == 1 and metrics["time_to_approval_seconds_mean"] == 1
    with pytest.raises(InvariantViolation):
        h.resume()
    assert len(h.executor.deliveries) == 1
    action = h.store.action(h.workspace.id, record.intent.action_id)
    with pytest.raises(InvariantViolation):
        asyncio.run(h.tools.invoke(h.workspace.id, h.run.id, action, h.run.version))
    assert len(h.executor.deliveries) == 1


@pytest.mark.parametrize("level", [0, 1, 4])
def test_low_and_unimplemented_autonomy_never_write(service, clock, level):
    h = GovernanceHarness(service, clock, autonomy=level)
    h.drive()
    assert not h.executor.deliveries
    assert h.record().intent.effect is ApprovalEffect.DENY
    assert not h.receipts()


@pytest.mark.parametrize("bounded,expected", [(False, "waiting"), (True, "succeeded")])
def test_level3_requires_explicit_bounded_policy(service, clock, bounded, expected):
    h = GovernanceHarness(service, clock, autonomy=3, bounded=bounded)
    assert h.drive().status == expected
    assert len(h.executor.deliveries) == int(bounded)
    if bounded:
        assert h.record().request is None


@pytest.mark.parametrize("risk", [ToolRisk.HIGH_RISK, ToolRisk.INTERNAL_WRITE, ToolRisk.READ_ONLY])
def test_fixture_cannot_launder_canonical_risk(service, clock, risk):
    h = GovernanceHarness(service, clock, autonomy=3, bounded=True, risk=risk)
    h.drive()
    assert not h.executor.deliveries


@pytest.mark.parametrize("change", ["message", "destination", "tool_version", "actor", "workspace"])
def test_fingerprint_binds_material_fields(service, clock, change):
    h = GovernanceHarness(service, clock)
    h.drive()
    h.review()
    r = h.record()
    action = h.store.action(h.workspace.id, r.intent.action_id)
    tool = replace(h.tool, version=Version(2)) if change == "tool_version" else h.tool
    request = FixtureMessageInput(
        "elsewhere" if change == "destination" else r.intent.destination,
        "altered" if change == "message" else "Your requested brief is ready.",
    )
    actor = AgentRunId("another-run") if change == "actor" else h.run.id
    workspace = service.create_workspace("foreign").id if change == "workspace" else h.workspace.id
    assert (
        fingerprint(workspace, actor, action.id, tool, input_json(request)) != r.intent.fingerprint
    )
    changed_run = replace(h.run, id=actor) if change == "actor" else h.run
    with pytest.raises((InvariantViolation, WorkspaceMismatch)):
        if change == "workspace":
            h.governance.decide(
                workspace, r.intent.id, r.intent.fingerprint, h.reviewer, DecisionKind.REVOKED
            )
        else:
            h.governance.validate(r, changed_run, action, tool, request)
    assert not h.executor.deliveries


@pytest.mark.parametrize(
    "kind", [DecisionKind.REJECTED, DecisionKind.REVOKED, DecisionKind.EXPIRED]
)
def test_rejected_revoked_expired_approval_cannot_execute(service, clock, kind):
    h = GovernanceHarness(service, clock)
    h.drive()
    if kind is DecisionKind.REJECTED:
        h.review(kind)
    else:
        h.review()
        if kind is DecisionKind.REVOKED:
            h.review(kind)
        else:
            clock.advance(timedelta(seconds=30))
    with pytest.raises(InvariantViolation):
        h.resume()
    assert h.record().decisions[-1].kind is kind
    assert not h.executor.deliveries and not h.receipts()
    assert service.store.get_goal(h.goal.id).status == "active"
    assert h.store.get_run(h.workspace.id, h.run.id).status == "waiting"


@pytest.mark.parametrize(
    "mutation",
    [
        "cancel_intent",
        "cancel_task",
        "cancel_execution",
        "cancel_run",
        "stale_version",
        "disable_tool",
        "policy",
        "missing_grant",
    ],
)
def test_current_state_revalidation_prevents_write(service, clock, mutation):
    h = GovernanceHarness(service, clock)
    h.drive()
    h.review()
    if mutation == "cancel_intent":
        h.governance.cancel(h.workspace.id, h.record().intent.id)
    elif mutation == "cancel_task":
        task = service.store.get_task(h.run.task_id)
        service.cancel_task(task.id, task.version)
    elif mutation == "cancel_execution":
        execution = service.store.get_execution(h.run.execution_id)
        service.cancel_execution(execution.id, execution.version)
    elif mutation == "cancel_run":
        h.runtime.cancel(h.workspace.id, h.run.id, h.run.version)
    elif mutation == "stale_version":
        h.run = replace(h.run, version=Version(1))
    elif mutation == "disable_tool":
        h.registry.set_enabled(h.workspace.id, h.tool.definition.id, False)
    elif mutation == "policy":
        h.store.publish_approval_policy(replace(h.policy, version=Version(2), enabled=False))
    else:
        # Defense against a corrupted adapter, without exposing a permission mutation command.
        h.store._runs[h.run.id] = replace(
            h.run, definition_version=replace(h.definition, allowed_tools=())
        )
    with pytest.raises(InvariantViolation):
        h.resume()
    assert not h.executor.deliveries and not h.receipts()


def test_tool_permission_is_independent_of_workspace_approval_policy(service, clock):
    h = GovernanceHarness(service, clock, grant=False, autonomy=3, bounded=True)
    h.drive()
    assert not h.executor.deliveries and not h.store.governed_actions(h.workspace.id)


@pytest.mark.parametrize("spoof", ["unknown", "foreign", "manager", "wrong_digest"])
def test_explicit_reviewer_and_exact_review_binding(service, clock, spoof):
    h = GovernanceHarness(service, clock)
    h.drive()
    r = h.record()
    reviewer = h.reviewer
    digest = r.intent.fingerprint
    if spoof == "foreign":
        reviewer = replace(reviewer, workspace_id=service.create_workspace("Other").id)
    elif spoof == "wrong_digest":
        digest = "0" * 64
    else:
        reviewer = replace(reviewer, id=ReviewerId(spoof))
    with pytest.raises(InvariantViolation):
        h.governance.decide(h.workspace.id, r.intent.id, digest, reviewer, DecisionKind.APPROVED)
    assert not h.record().decisions and not h.executor.deliveries


def test_normal_context_resume_cannot_skip_approval(service, clock):
    h = GovernanceHarness(service, clock)
    h.drive()
    with pytest.raises(InvariantViolation):
        h.runtime.resume(h.workspace.id, h.run.id, h.run.version, h.run.context)
    assert not h.executor.deliveries


def test_immutable_records_reject_payload_and_decision_forgery(service, clock):
    h = GovernanceHarness(service, clock)
    h.drive()
    r = h.record()
    with pytest.raises(FrozenInstanceError):
        r.intent.destination = "elsewhere"
    with pytest.raises(InvariantViolation):
        replace(r.intent, arguments_json='{"message":"changed"}')
    with pytest.raises(InvariantViolation):
        h.store.save_governed_action(
            replace(r, intent=replace(r.intent, destination="elsewhere"), version=r.version.next()),
            r.version,
        )


@pytest.mark.parametrize("phase", ["request", "decision", "claim"])
def test_atomic_governance_persistence_prevents_partial_authority(
    service, clock, monkeypatch, phase
):
    h = GovernanceHarness(service, clock)
    if phase != "request":
        h.drive()
    if phase == "claim":
        h.review()
    before = h.store.governed_actions(h.workspace.id)
    original = h.store.append_event
    target = {
        "request": EventType.APPROVAL_REQUESTED,
        "decision": EventType.APPROVAL_GRANTED,
        "claim": EventType.ACTION_EXECUTION_AUTHORIZED,
    }[phase]

    def fail(event):
        if event.event_type is target:
            raise RuntimeError("injected persistence fault")
        original(event)

    monkeypatch.setattr(h.store, "append_event", fail)
    if phase == "request":
        h.drive()  # Runtime records normalized failure after rollback.
    else:
        with pytest.raises(RuntimeError):
            h.review() if phase == "decision" else h.resume()
    assert h.store.governed_actions(h.workspace.id) == before
    assert not h.executor.deliveries
    assert not h.store.tool_invocations(h.workspace.id, h.run.id)
    if phase == "claim":
        assert h.store.get_run(h.workspace.id, h.run.id).status == "waiting"
        assert service.store.get_execution(h.run.execution_id).status == "waiting"


def test_duplicate_execution_and_cancel_claim_race(service, clock):
    async def scenario():
        gate, entered = asyncio.Event(), asyncio.Event()
        executor = FakeToolExecutor(
            (output_json(ToolOutput("customer:paper-kite", (), "ok")),), gate=gate, entered=entered
        )
        h = GovernanceHarness(service, clock, executor=executor)
        h.run = await h.runtime.drive(h.workspace.id, h.run.id, h.run.version)
        h.review()
        task = asyncio.create_task(
            h.tools.resume_intent(h.workspace.id, h.run.id, h.record().intent.id, h.run.version)
        )
        await asyncio.wait_for(entered.wait(), 2)
        with pytest.raises(InvariantViolation):
            await h.tools.resume_intent(
                h.workspace.id, h.run.id, h.record().intent.id, h.run.version
            )
        with pytest.raises(InvariantViolation):
            h.governance.cancel(h.workspace.id, h.record().intent.id)
        with pytest.raises(InvariantViolation):
            h.review(DecisionKind.REVOKED)
        gate.set()
        await task
        assert len(executor.invocations) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "error,expected", [(TimeoutError(), "outcome_unknown"), (None, "observed_failure")]
)
def test_outcome_certainty_never_infers_no_write_from_timeout(service, clock, error, expected):
    executor = FakeToolExecutor((error,)) if error else FixtureMessageExecutor(reject=True)
    h = GovernanceHarness(service, clock, executor=executor)
    h.drive()
    h.review()
    asyncio.run(
        h.tools.resume_intent(h.workspace.id, h.run.id, h.record().intent.id, h.run.version)
    )
    r = h.record()
    exported = serialize_governed_action(r, h.receipts())
    if expected == "observed_failure":
        assert h.receipts()[0].remote_outcome == "observed_failure"
        assert exported["outcome"] == expected
    else:
        assert exported["outcome"] == expected
    assert r.consumed and r.invocation_id is not None


def test_injection_cannot_smuggle_approval_flags(service, clock):
    h = GovernanceHarness(service, clock)
    h.runtime.model = FakeModel((h.proposal(approved=True),))
    h.drive()
    assert not h.executor.deliveries
    assert not h.receipts()


def test_normalization_is_deterministic_but_message_whitespace_material(service, clock):
    h = GovernanceHarness(service, clock)
    first = validate_input('{"message":"Hello", "destination":"customer:paper-kite"}', h.tool)
    second = validate_input('{ "destination": "customer:paper-kite", "message": "Hello" }', h.tool)
    assert input_json(first) == input_json(second)
    changed = validate_input('{"message":"Hello ","destination":"customer:paper-kite"}', h.tool)
    assert input_json(first) != input_json(changed)


@pytest.mark.parametrize("rejected,graph_changed", [(False, False), (True, False), (False, True)])
def test_department_orchestration_approval_demo(service, clock, rejected, graph_changed):
    from agent_company_os.adapters.agent_selector import DeterministicAgentSelector
    from agent_company_os.adapters.orchestration_store import InMemoryOrchestrationStore
    from agent_company_os.adapters.orchestration_strategy import FakeOrchestrationStrategy
    from agent_company_os.adapters.organization_store import InMemoryOrganizationStore
    from agent_company_os.adapters.result_aggregator import DeterministicResultAggregator
    from agent_company_os.application.orchestration import OrchestrationService
    from agent_company_os.application.organization import AgentRegistry, OrganizationService
    from agent_company_os.domain.orchestration import AgentRequirements, PlannedTask, PlanProposal
    from agent_company_os.domain.organization import (
        Department,
        DepartmentMembership,
        DepartmentRoute,
        OrganizationGraphVersion,
        OrganizationPolicy,
        OrgRole,
        RegisteredAgent,
        RouteKind,
    )

    workspace = service.create_workspace("Aurora Desk governed delivery")
    goal = service.create_goal(
        CreateGoalCommand(
            workspace.id,
            "Prepare and deliver a customer competitor brief",
            ("Grounded and approved delivery",),
        )
    )
    goal = service.activate_goal(goal.id, goal.version)
    store = InMemoryRuntimeStore(service.store)
    tools = ToolRegistry()
    executor = FixtureMessageExecutor()
    tool = ToolVersion(
        ToolDefinition(
            ToolId("fixture-message"),
            workspace.id,
            "Fixture message",
            "No external integration",
            ToolRisk.EXTERNAL_WRITE,
        ),
        Version(1),
        ExecutorKind.SEND_FIXTURE_MESSAGE,
        "send_fixture_message.v1",
    )
    tools.publish(tool, executor)
    definitions = tuple(
        replace(
            research_brief_agent(workspace.id, AgentDefinitionId(name)),
            role=name,
            autonomy_ceiling=2,
            allowed_actions=tuple(ActionType),
            allowed_tools=(tool.grant,) if name == "Marketing" else (),
        )
        for name in ("Research", "Product", "Marketing")
    )
    for d in definitions:
        store.publish(d)
    org_store = InMemoryOrganizationStore(store)
    org = OrganizationService(org_store, clock, service.ids)
    graph = org.create(workspace.id, "Aurora Desk")
    departments = tuple(
        Department(service.ids.department_id(), workspace.id, d.role) for d in definitions
    )
    role = OrgRole(service.ids.org_role_id(), workspace.id, "specialist")
    v1 = OrganizationGraphVersion(
        graph.id,
        workspace.id,
        Version(1),
        clock.now(),
        departments,
        (role,),
        (),
        tuple(RegisteredAgent(workspace.id, d.definition.id, d.version) for d in definitions),
        tuple(
            DepartmentMembership(workspace.id, d.definition.id, department.id, role.id)
            for d, department in zip(definitions, departments, strict=True)
        ),
        (),
        OrganizationPolicy(
            tuple(
                DepartmentRoute(a.id, b.id, RouteKind.DELEGATE, True)
                for a in departments
                for b in departments
                if a != b
            )
        ),
    )
    org.publish(v1, graph.revision)
    org.activate(workspace.id, Version(1), org_store.graph(workspace.id).revision)
    registry = AgentRegistry(org_store, clock)
    governance = GovernanceService(store, clock, service.ids, registry)
    reviewer = ReviewerPrincipal(ReviewerId("fixture-reviewer"), workspace.id)
    store.publish_approval_policy(
        ApprovalPolicy(
            workspace.id, Version(1), (tool.grant,), ("customer:paper-kite",), (reviewer,)
        )
    )
    runtime = AgentRuntimeService(
        store,
        clock,
        service.ids,
        FakeModel(()),
        ToolRuntimeService(store, tools, clock, service.ids, governance),
    )
    orchestration_store = InMemoryOrchestrationStore(store)
    planned = tuple(
        PlannedTask(
            d.role,
            d.role,
            ("pricing",),
            dependencies=(definitions[i - 1].role,) if i else (),
            requirements=AgentRequirements(required_department=departments[i].id),
        )
        for i, d in enumerate(definitions)
    )
    orchestration = OrchestrationService(
        orchestration_store,
        FakeOrchestrationStrategy((PlanProposal(workspace.id, goal.id, planned),)),
        DeterministicAgentSelector(store),
        DeterministicResultAggregator(),
        runtime,
        clock,
        service.ids,
        registry,
    )
    run = asyncio.run(orchestration.start(workspace.id, goal.id))
    materialization = orchestration.materialize(workspace.id, run.id, run.version)
    for index, lineage in enumerate(materialization.tasks):
        run = orchestration_store.run(workspace.id, run.id)
        delegation = orchestration.delegate(workspace.id, run.id, lineage.task_id, run.version)
        assert delegation is not None
        context, _ = orchestration.context_for_task(
            workspace.id,
            run.id,
            lineage.task_id,
            ("pricing",),
            (Fact("pricing", "$49/month", "approved_001"),) if index == 0 else (),
        )
        finish = complete(context.facts[0].source_id)
        responses = (
            (
                call(
                    str(tool.definition.id),
                    {"destination": "customer:paper-kite", "message": "Your brief is ready."},
                ),
                finish,
            )
            if index == 2
            else (finish,)
        )
        runtime.model = FakeModel(responses)
        result = asyncio.run(
            orchestration.execute(workspace.id, run.id, delegation.id, run.version, context)
        )
        if index < 2:
            assert result.status == "succeeded"
    run = orchestration_store.run(workspace.id, run.id)
    assert delegation is not None
    assert result.status == "waiting" and run.escalation_reason == "approval_required"
    assert not executor.deliveries and service.store.get_goal(goal.id).status == "active"
    record = store.governed_actions(workspace.id)[0]
    governance.decide(
        workspace.id,
        record.intent.id,
        record.intent.fingerprint,
        reviewer,
        DecisionKind.REJECTED if rejected else DecisionKind.APPROVED,
    )
    if graph_changed:
        org.publish(replace(v1, version=Version(2)), org_store.graph(workspace.id).revision)
        org.activate(workspace.id, Version(2), org_store.graph(workspace.id).revision)
    if rejected or graph_changed:
        with pytest.raises(InvariantViolation):
            asyncio.run(
                orchestration.resume_delegation(
                    workspace.id, run.id, delegation.id, run.version, context, record.intent.id
                )
            )
        assert orchestration_store.run(workspace.id, run.id).status == "waiting"
        assert service.store.get_goal(goal.id).status == "active"
        assert not executor.deliveries
    else:
        resumed = asyncio.run(
            orchestration.resume_delegation(
                workspace.id, run.id, delegation.id, run.version, context, record.intent.id
            )
        )
        assert resumed.id == result.id and resumed.deadline == result.deadline
        assert resumed.working_state.iteration == 2
        assert orchestration_store.run(workspace.id, run.id).status == "completed"
        assert service.store.get_goal(goal.id).status == "satisfied"
        assert len(executor.deliveries) == 1


def test_handoff_ends_actor_and_approved_intent_cannot_follow(service, clock):
    h = GovernanceHarness(service, clock)
    h.drive()
    h.review()
    h.runtime.yield_for_handoff(h.workspace.id, h.run.id, h.run.version)
    with pytest.raises(InvariantViolation):
        h.resume()
    assert not h.executor.deliveries
    assert service.store.get_task(h.task.id).status == "ready"


def test_unknown_write_cannot_complete_task_from_unrelated_evidence(service, clock):
    h = GovernanceHarness(service, clock, executor=FakeToolExecutor((TimeoutError(),)))
    h.drive()
    h.review()
    assert h.resume().status == "failed"
    assert h.run.error_code == "consequential_action_unresolved"
    assert service.store.get_goal(h.goal.id).status == "active"


def test_claim_fault_never_creates_receipt_or_allows_repeat_dispatch(service, clock, monkeypatch):
    h = GovernanceHarness(service, clock)
    h.drive()
    h.review()
    original = h.store.finish_tool_invocation
    failures: list[object] = []

    def fail_once(receipt):
        if not failures:
            failures.append(receipt.id)
            raise RuntimeError("result commit failed")
        original(receipt)

    monkeypatch.setattr(h.store, "finish_tool_invocation", fail_once)
    with pytest.raises(RuntimeError):
        h.resume()
    assert len(h.executor.deliveries) == 1
    assert h.receipts()[0].remote_outcome == "unknown"
    assert h.record().consumed
    with pytest.raises(InvariantViolation):
        h.resume()
    assert len(h.executor.deliveries) == 1


def test_level1_can_recommend_without_creating_write_authority(service, clock):
    from test_tools import decision

    h = GovernanceHarness(
        service,
        clock,
        autonomy=1,
        responses=(
            decision(
                "respond", {"message": "Recommend delivering the brief; a human must perform it."}
            ),
            complete("approved_001"),
        ),
    )
    assert h.drive().status == "succeeded"
    assert not h.store.governed_actions(h.workspace.id)
    assert not h.executor.deliveries


@pytest.mark.parametrize(
    "dimension", ["destination", "no_governance", "missing_policy", "expired_pending"]
)
def test_fail_closed_configuration_and_expiry(service, clock, dimension):
    h = GovernanceHarness(service, clock)
    if dimension == "destination":
        h.runtime.model = FakeModel(
            (h.proposal(destination="customer:unapproved"), complete("approved_001"))
        )
    elif dimension == "no_governance":
        h.tools.governance = None
    elif dimension == "missing_policy":
        h.store._approval_policies.clear()
    h.drive()
    if dimension == "expired_pending":
        clock.advance(timedelta(seconds=30))
        with pytest.raises(InvariantViolation):
            h.resume()
        assert h.record().decisions[-1].kind is DecisionKind.EXPIRED
    assert not h.executor.deliveries


@pytest.mark.parametrize(
    "dimension", ["expiry_zero", "expiry_large", "destinations", "reviewers", "boolean_autonomy"]
)
def test_governance_hard_bounds(service, clock, dimension):
    h = GovernanceHarness(service, clock)
    with pytest.raises(InvariantViolation):
        if dimension == "expiry_zero":
            replace(h.policy, expiry_seconds=0)
        elif dimension == "expiry_large":
            replace(h.policy, expiry_seconds=301)
        elif dimension == "destinations":
            replace(h.policy, destinations=tuple(str(i) for i in range(11)))
        elif dimension == "reviewers":
            replace(h.policy, reviewers=(h.reviewer,) * 11)
        else:
            replace(h.definition, autonomy_ceiling=True)


def test_cancel_after_fixture_write_preserves_unknown_and_prevents_replay(service, clock):
    async def scenario():
        gate, entered = asyncio.Event(), asyncio.Event()
        fixture = FixtureMessageExecutor()

        class DelayedReceipt:
            async def execute(self, request, context):
                raw = await fixture.execute(request, context)
                entered.set()
                await gate.wait()
                return raw

        h = GovernanceHarness(service, clock, executor=DelayedReceipt())
        h.run = await h.runtime.drive(h.workspace.id, h.run.id, h.run.version)
        h.review()
        dispatch = asyncio.create_task(
            h.tools.resume_intent(h.workspace.id, h.run.id, h.record().intent.id, h.run.version)
        )
        await asyncio.wait_for(entered.wait(), 2)
        current = h.store.get_run(h.workspace.id, h.run.id)
        h.runtime.cancel(h.workspace.id, current.id, current.version)
        gate.set()
        result = await dispatch
        assert result.status == "cancelled"
        assert len(fixture.deliveries) == 1
        assert h.receipts()[0].remote_outcome == "unknown"
        assert serialize_governed_action(h.record(), h.receipts())["outcome"] == "outcome_unknown"
        with pytest.raises(InvariantViolation):
            await h.tools.resume_intent(
                h.workspace.id, h.run.id, h.record().intent.id, result.version
            )
        assert len(fixture.deliveries) == 1

    asyncio.run(scenario())


def test_approval_metadata_does_not_log_message_content(service, clock):
    h = GovernanceHarness(service, clock)
    h.drive()
    h.review()
    h.resume()
    audit = repr(h.store.events(h.workspace.id))
    assert "Your requested brief is ready." not in audit
    assert h.record().intent.fingerprint in audit
