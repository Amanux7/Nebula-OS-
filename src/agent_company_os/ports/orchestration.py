"""Replaceable planning, selection, aggregation, and persistence seams."""

from contextlib import AbstractContextManager
from typing import Protocol

from agent_company_os.domain.agent import AgentDefinitionVersion
from agent_company_os.domain.events import Event
from agent_company_os.domain.ids import GoalId, Version, WorkspaceId
from agent_company_os.domain.orchestration import (
    AgentRequirements,
    Delegation,
    DelegationAttempt,
    DelegationId,
    GoalResultDraft,
    OrchestrationPlanId,
    OrchestrationRequest,
    OrchestrationRun,
    OrchestrationRunId,
    PlanMaterialization,
    PlanProposal,
    PlanVersion,
    TaskResultReference,
)
from agent_company_os.ports.runtime_store import RuntimeStore


class OrchestrationStrategyPort(Protocol):
    @property
    def strategy_id(self) -> str: ...
    @property
    def strategy_version(self) -> str: ...
    async def plan(self, request: OrchestrationRequest) -> PlanProposal: ...


class AgentSelector(Protocol):
    def select(
        self,
        workspace_id: WorkspaceId,
        requirements: AgentRequirements,
        candidates: tuple[AgentDefinitionVersion, ...],
        excluded: tuple[AgentDefinitionVersion, ...] = (),
    ) -> AgentDefinitionVersion: ...


class ResultAggregator(Protocol):
    def aggregate(
        self, goal_id: GoalId, required_count: int, results: tuple[TaskResultReference, ...]
    ) -> GoalResultDraft: ...


class OrchestrationStore(Protocol):
    runtime: RuntimeStore

    def atomic(self) -> AbstractContextManager[None]: ...
    def add_run(self, run: OrchestrationRun) -> None: ...
    def run(self, workspace_id: WorkspaceId, run_id: OrchestrationRunId) -> OrchestrationRun: ...
    def save_run(self, run: OrchestrationRun, expected: Version) -> None: ...
    def add_plan(self, plan: PlanVersion) -> None: ...
    def plan(
        self, workspace_id: WorkspaceId, plan_id: OrchestrationPlanId, version: Version
    ) -> PlanVersion: ...
    def plans(
        self, workspace_id: WorkspaceId, run_id: OrchestrationRunId
    ) -> tuple[PlanVersion, ...]: ...
    def add_materialization(self, materialization: PlanMaterialization) -> None: ...
    def materialization(
        self, workspace_id: WorkspaceId, plan_id: OrchestrationPlanId, version: Version
    ) -> PlanMaterialization: ...
    def add_delegation(self, delegation: Delegation) -> None: ...
    def delegation(self, workspace_id: WorkspaceId, delegation_id: DelegationId) -> Delegation: ...
    def delegations(
        self, workspace_id: WorkspaceId, run_id: OrchestrationRunId
    ) -> tuple[Delegation, ...]: ...
    def add_attempt(self, workspace_id: WorkspaceId, attempt: DelegationAttempt) -> None: ...
    def attempts(
        self, workspace_id: WorkspaceId, delegation_id: DelegationId
    ) -> tuple[DelegationAttempt, ...]: ...
    def append_event(self, event: Event) -> None: ...
