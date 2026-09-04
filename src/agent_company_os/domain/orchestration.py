"""Bounded plans and assignments; coordination is not execution authority."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from agent_company_os.domain.agent import AgentDefinitionId, AgentRunId
from agent_company_os.domain.errors import InvalidStateTransition, InvariantViolation
from agent_company_os.domain.ids import (
    ExecutionId,
    GoalId,
    OpaqueId,
    TaskAttemptId,
    TaskId,
    Version,
    WorkspaceId,
)
from agent_company_os.domain.knowledge import KnowledgeSourceId
from agent_company_os.domain.memory import MemoryScope
from agent_company_os.domain.tools import ToolId
from agent_company_os.domain.validation import clean_required_text, require_utc


class OrchestrationRunId(OpaqueId):
    pass


class OrchestrationPlanId(OpaqueId):
    pass


class DelegationId(OpaqueId):
    pass


@dataclass(frozen=True)
class OrchestrationPolicy:
    max_tasks: int = 8
    max_dependencies_per_task: int = 3
    max_dependency_depth: int = 5
    max_plan_text: int = 4000
    max_replans: int = 2
    max_iterations: int = 20
    max_parallel_width: int = 3
    max_agent_runs: int = 12
    max_failed_attempts: int = 3
    max_retries_per_task: int = 1
    max_redelegations_per_task: int = 1
    planner_seconds: int = 5
    allowed_agent_ids: tuple[AgentDefinitionId, ...] = ()
    allowed_roles: tuple[str, ...] = ()
    version: str = "bounded-orchestration-v1"

    def __post_init__(self) -> None:
        bounds = (
            (self.max_tasks, 20),
            (self.max_dependencies_per_task, 10),
            (self.max_dependency_depth, 10),
            (self.max_plan_text, 16000),
            (self.max_replans, 5),
            (self.max_iterations, 100),
            (self.max_parallel_width, 10),
            (self.max_agent_runs, 50),
            (self.max_failed_attempts, 20),
            (self.max_retries_per_task, 5),
            (self.max_redelegations_per_task, 5),
            (self.planner_seconds, 30),
        )
        if any(type(value) is not int or not 1 <= value <= maximum for value, maximum in bounds):
            raise InvariantViolation("orchestration_policy_bounds")
        if len(set(self.allowed_agent_ids)) != len(self.allowed_agent_ids):
            raise InvariantViolation("orchestration_agent_allowlist_unique")


@dataclass(frozen=True)
class AgentRequirements:
    capabilities: tuple[str, ...] = ()
    tool_ids: tuple[ToolId, ...] = ()
    knowledge_source_ids: tuple[KnowledgeSourceId, ...] = ()
    memory_scopes: tuple[MemoryScope, ...] = ()
    min_autonomy: int = 0

    def __post_init__(self) -> None:
        collections = (
            self.capabilities,
            self.tool_ids,
            self.knowledge_source_ids,
            self.memory_scopes,
        )
        if (
            any(not isinstance(items, tuple) or len(items) > 10 for items in collections)
            or any(len(set(items)) != len(items) for items in collections)
            or any(
                not capability or len(capability) > 64 or capability != capability.casefold()
                for capability in self.capabilities
            )
            or self.min_autonomy not in (0, 1, 2)
        ):
            raise InvariantViolation("agent_requirements_bound")


@dataclass(frozen=True)
class PlannedTask:
    id: str
    title: str
    acceptance_criteria: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    requirements: AgentRequirements = AgentRequirements()
    priority: int = 0
    required: bool = True

    def __post_init__(self) -> None:
        clean_required_text(self.id, "planned_task_id")
        clean_required_text(self.title, "planned_task_title")
        if (
            len(self.id) > 64
            or len(self.title) > 200
            or not self.acceptance_criteria
            or len(self.acceptance_criteria) > 5
            or any(not item or len(item) > 500 for item in self.acceptance_criteria)
            or not isinstance(self.dependencies, tuple)
            or len(set(self.dependencies)) != len(self.dependencies)
            or type(self.priority) is not int
            or not 0 <= self.priority <= 100
            or type(self.required) is not bool
        ):
            raise InvariantViolation("planned_task_bounds")


@dataclass(frozen=True)
class PlanProposal:
    workspace_id: WorkspaceId
    goal_id: GoalId
    tasks: tuple[PlannedTask, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.tasks, tuple) or self.schema_version != 1:
            raise InvariantViolation("plan_schema_version")


@dataclass(frozen=True)
class AgentCatalogItem:
    definition_id: AgentDefinitionId
    version: Version
    workspace_id: WorkspaceId
    role: str
    capabilities: tuple[str, ...]
    tool_ids: tuple[ToolId, ...]
    knowledge_source_ids: tuple[KnowledgeSourceId, ...]
    memory_scopes: tuple[MemoryScope, ...]
    autonomy_ceiling: int


@dataclass(frozen=True)
class OrchestrationRequest:
    workspace_id: WorkspaceId
    goal_id: GoalId
    goal_version: Version
    objective: str
    constraints: tuple[str, ...]
    agents: tuple[AgentCatalogItem, ...]
    policy: OrchestrationPolicy


@dataclass(frozen=True)
class PlanVersion:
    id: OrchestrationPlanId
    workspace_id: WorkspaceId
    goal_id: GoalId
    orchestration_run_id: OrchestrationRunId
    version: Version
    strategy_id: str
    strategy_version: str
    policy_version: str
    goal_version: Version
    proposal: PlanProposal
    created_at: datetime
    schema_version: int = 1

    def __post_init__(self) -> None:
        require_utc(self.created_at, "created_at")
        if (
            self.proposal.workspace_id != self.workspace_id
            or self.proposal.goal_id != self.goal_id
            or self.schema_version != 1
        ):
            raise InvariantViolation("plan_version_binding")


@dataclass(frozen=True)
class MaterializedTask:
    plan_id: OrchestrationPlanId
    plan_version: Version
    planned_task_id: str
    task_id: TaskId


@dataclass(frozen=True)
class PlanMaterialization:
    workspace_id: WorkspaceId
    orchestration_run_id: OrchestrationRunId
    plan_id: OrchestrationPlanId
    plan_version: Version
    tasks: tuple[MaterializedTask, ...]
    materialized_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.materialized_at, "materialized_at")
        if len({item.planned_task_id for item in self.tasks}) != len(self.tasks):
            raise InvariantViolation("materialization_unique_planned_tasks")


class OrchestrationStatus(StrEnum):
    PLANNING = "planning"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class OrchestrationRun:
    id: OrchestrationRunId
    workspace_id: WorkspaceId
    goal_id: GoalId
    strategy_id: str
    strategy_version: str
    policy: OrchestrationPolicy
    created_at: datetime
    status: OrchestrationStatus = OrchestrationStatus.PLANNING
    version: Version = Version(1)
    plan_id: OrchestrationPlanId | None = None
    current_plan_version: Version | None = None
    execution_id: ExecutionId | None = None
    replan_count: int = 0
    agent_run_count: int = 0
    failed_attempt_count: int = 0
    escalation_reason: str | None = None
    ended_at: datetime | None = None

    def __post_init__(self) -> None:
        require_utc(self.created_at, "created_at")
        terminal = self.status in {
            OrchestrationStatus.COMPLETED,
            OrchestrationStatus.FAILED,
            OrchestrationStatus.CANCELLED,
        }
        if terminal != (self.ended_at is not None):
            raise InvariantViolation("orchestration_terminal_time")
        if (
            self.replan_count > self.policy.max_replans
            or self.agent_run_count > self.policy.max_agent_runs
        ):
            raise InvariantViolation("orchestration_budget_exceeded")

    def evolve(
        self,
        *,
        at: datetime,
        status: OrchestrationStatus | None = None,
        plan_id: OrchestrationPlanId | None = None,
        plan_version: Version | None = None,
        execution_id: ExecutionId | None = None,
        replan_delta: int = 0,
        agent_run_delta: int = 0,
        failed_delta: int = 0,
        escalation_reason: str | None = None,
    ) -> OrchestrationRun:
        target = status or self.status
        allowed = {
            OrchestrationStatus.PLANNING: {
                OrchestrationStatus.RUNNING,
                OrchestrationStatus.WAITING,
                OrchestrationStatus.FAILED,
                OrchestrationStatus.CANCELLED,
            },
            OrchestrationStatus.RUNNING: {
                OrchestrationStatus.PLANNING,
                OrchestrationStatus.WAITING,
                OrchestrationStatus.COMPLETED,
                OrchestrationStatus.FAILED,
                OrchestrationStatus.CANCELLED,
            },
            OrchestrationStatus.WAITING: {
                OrchestrationStatus.RUNNING,
                OrchestrationStatus.PLANNING,
                OrchestrationStatus.FAILED,
                OrchestrationStatus.CANCELLED,
            },
        }
        if target != self.status and target not in allowed.get(self.status, set()):
            raise InvalidStateTransition("OrchestrationRun", str(self.id), self.status, target)
        require_utc(at, "at")
        return replace(
            self,
            status=target,
            version=self.version.next(),
            plan_id=plan_id or self.plan_id,
            current_plan_version=plan_version or self.current_plan_version,
            execution_id=execution_id or self.execution_id,
            replan_count=self.replan_count + replan_delta,
            agent_run_count=self.agent_run_count + agent_run_delta,
            failed_attempt_count=self.failed_attempt_count + failed_delta,
            escalation_reason=escalation_reason,
            ended_at=at
            if target
            in {
                OrchestrationStatus.COMPLETED,
                OrchestrationStatus.FAILED,
                OrchestrationStatus.CANCELLED,
            }
            else None,
        )


class DelegationStatus(StrEnum):
    ASSIGNED = "assigned"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Delegation:
    id: DelegationId
    workspace_id: WorkspaceId
    orchestration_run_id: OrchestrationRunId
    plan_id: OrchestrationPlanId
    plan_version: Version
    planned_task_id: str
    task_id: TaskId
    agent_definition_id: AgentDefinitionId
    agent_definition_version: Version
    created_at: datetime
    status: DelegationStatus = DelegationStatus.ASSIGNED
    version: Version = Version(1)
    retry_ordinal: int = 0
    redelegation_ordinal: int = 0

    def __post_init__(self) -> None:
        require_utc(self.created_at, "created_at")


@dataclass(frozen=True)
class DelegationAttempt:
    delegation_id: DelegationId
    execution_id: ExecutionId
    task_attempt_id: TaskAttemptId
    agent_run_id: AgentRunId


@dataclass(frozen=True)
class TaskResultReference:
    source_task_id: TaskId
    source_attempt_id: TaskAttemptId
    source_agent_run_id: AgentRunId
    result_version: Version
    source_references: tuple[str, ...]

    @property
    def reference(self) -> str:
        return (
            f"task_result:{self.source_task_id}:{self.source_attempt_id}:"
            f"{self.source_agent_run_id}:v{self.result_version.value}"
        )


@dataclass(frozen=True)
class GoalResultDraft:
    goal_id: GoalId
    task_results: tuple[TaskResultReference, ...]
    complete: bool
