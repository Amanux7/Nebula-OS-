"""Offline collaboration walkthrough populated only through application commands."""

import asyncio
import json

from agent_company_os.adapters.agent_selector import DeterministicAgentSelector
from agent_company_os.adapters.fake_model import FakeModel
from agent_company_os.adapters.orchestration_strategy import FakeOrchestrationStrategy
from agent_company_os.adapters.result_aggregator import DeterministicResultAggregator
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.application.communication import AgentCommunicationService
from agent_company_os.application.orchestration import OrchestrationService
from agent_company_os.application.organization import AgentRegistry
from agent_company_os.application.runtime import AgentRuntimeService
from agent_company_os.application.service import (
    CreateExecutionCommand,
    CreateGoalCommand,
    DomainService,
)
from agent_company_os.domain.agent import AgentRun, Fact, SuppliedContext
from agent_company_os.domain.communication import (
    CommunicationPolicy,
    HandoffRequestPayload,
    InformationPayload,
    MessageKind,
)
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.ids import WorkspaceId
from agent_company_os.domain.orchestration import (
    AgentRequirements,
    Delegation,
    PlannedTask,
    PlanProposal,
)
from agent_company_os.domain.organization import CapabilityDefinition, Department
from agent_company_os.ports.clock import Clock
from agent_company_os.ports.ids import IdGenerator


def seed_collaboration(
    group: SqliteStoreGroup,
    workspace: WorkspaceId,
    clock: Clock,
    ids: IdGenerator,
    departments: tuple[Department, ...],
    capabilities: tuple[CapabilityDefinition, ...],
    inspection_marker: str | None = None,
) -> None:
    domain = DomainService(group.domain, clock, ids)
    goal = domain.create_goal(
        CreateGoalCommand(
            workspace, "Aurora Desk cross-department competitor brief", ("Three grounded sections",)
        )
    )
    goal = domain.activate_goal(goal.id, goal.version)
    tasks = tuple(
        PlannedTask(
            name,
            title,
            ("fact",),
            requirements=AgentRequirements(
                capability_ids=(capabilities[i].id,), preferred_department=departments[i].id
            ),
        )
        for i, (name, title) in enumerate(
            (
                ("research", "Research alternatives"),
                ("product", "Analyze product fit"),
                ("marketing", "Write the competitor brief"),
            )
        )
    )
    runtime = AgentRuntimeService(group.runtime, clock, ids, FakeModel(()))
    orchestration = OrchestrationService(
        group.orchestration,
        FakeOrchestrationStrategy((PlanProposal(workspace, goal.id, tasks),)),
        DeterministicAgentSelector(group.runtime),
        DeterministicResultAggregator(),
        runtime,
        clock,
        ids,
        AgentRegistry(group.organization, clock),
    )
    parent = asyncio.run(orchestration.start(workspace, goal.id))
    orchestration.materialize(workspace, parent.id, parent.version)
    communication = AgentCommunicationService(group.communication, orchestration, clock, ids)
    runtime.communication = communication
    runs: list[AgentRun] = []
    delegations: list[Delegation] = []
    for task in orchestration.ready_tasks(workspace, parent.id):
        current = group.orchestration.run(workspace, parent.id)
        delegation = orchestration.delegate(workspace, parent.id, task.id, current.version)
        if delegation is None:
            raise InvariantViolation("demo_delegation_missing")
        current = group.orchestration.run(workspace, parent.id)
        execution = domain.create_execution(
            CreateExecutionCommand(workspace, goal.id, "synthetic-collaboration", 2)
        )
        execution = domain.start_execution(execution.id, execution.version)
        run = orchestration.start_delegation(
            workspace,
            parent.id,
            delegation.id,
            current.version,
            SuppliedContext(workspace, task.id, ("fact",), (Fact("fact", "verified", "fixture"),)),
            execution_id=execution.id,
        )
        runs.append(run)
        delegations.append(delegation)
    sender = next(r for r in runs if r.definition_version.role == "research")
    recipient = next(r for r in runs if r.definition_version.role == "product")
    thread = communication.create_thread(
        workspace, parent.id, sender.id, "Synthetic pricing clarification"
    )
    current = group.orchestration.run(workspace, parent.id)
    policy = CommunicationPolicy()
    communication.send(
        workspace,
        parent.id,
        thread.id,
        sender.id,
        recipient.id,
        MessageKind.INFORMATION,
        InformationPayload("Synthetic evidence needs a product review."),
        (),
        inspection_marker or "aurora-clarification",
        policy,
        sender_expected=sender.version,
        recipient_expected=recipient.version,
        orchestration_expected=current.version,
    )
    sender = group.runtime.get_run(workspace, sender.id)
    current = group.orchestration.run(workspace, parent.id)
    original = next(d for d in delegations if d.task_id == sender.task_id)
    handoff = communication.request_handoff(
        workspace,
        parent.id,
        sender.id,
        original.id,
        HandoffRequestPayload(
            "product_review",
            "Have Product verify the research section",
            AgentRequirements(
                capability_ids=(capabilities[0].id,), required_department=departments[1].id
            ),
        ),
        (),
        policy,
        sender_expected=sender.version,
        orchestration_expected=current.version,
    )
    accepted = communication.resolve_handoff(
        workspace, handoff.id, handoff.version, current.version, policy
    )
    if accepted.resulting_delegation_id is None:
        raise InvariantViolation("demo_handoff_not_accepted")
    completion = json.dumps(
        {
            "schema_version": 1,
            "action_type": "complete_task",
            "payload": {
                "findings": [{"key": "fact", "value": "verified", "source_id": "fixture"}],
                "gaps": [],
            },
        }
    )
    for run in runs:
        if run.id == sender.id:
            continue
        current_run = group.runtime.get_run(workspace, run.id)
        runtime.model = FakeModel((completion,))
        result = asyncio.run(runtime.drive(workspace, run.id, current_run.version))
        current = group.orchestration.run(workspace, parent.id)
        orchestration.reconcile_child(workspace, parent.id, result.id, current.version)
    runtime.model = FakeModel((completion,))
    current = group.orchestration.run(workspace, parent.id)
    asyncio.run(
        orchestration.execute(
            workspace,
            parent.id,
            accepted.resulting_delegation_id,
            current.version,
            SuppliedContext(
                workspace, sender.task_id, ("fact",), (Fact("fact", "verified", "fixture"),)
            ),
        )
    )
    communication.complete_handoff(workspace, accepted.id, accepted.version)
