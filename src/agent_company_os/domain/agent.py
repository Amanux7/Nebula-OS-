"""Immutable configuration and bounded runtime identity; no provider dependency."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

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
from agent_company_os.domain.knowledge import EvidencePackId, KnowledgeScope
from agent_company_os.domain.memory import MemoryAccessPolicy, MemoryContextPackId
from agent_company_os.domain.tools import ToolGrant, ToolObservationData
from agent_company_os.domain.validation import clean_required_text, require_utc


class AgentDefinitionId(OpaqueId):
    pass


class AgentRunId(OpaqueId):
    pass


class ActionId(OpaqueId):
    pass


class ObservationId(OpaqueId):
    pass


class ActionType(StrEnum):
    CALL_TOOL = "call_tool"
    RESPOND = "respond"
    COMPLETE_TASK = "complete_task"
    REQUEST_MORE_CONTEXT = "request_more_context"


@dataclass(frozen=True)
class AgentDefinition:
    id: AgentDefinitionId
    workspace_id: WorkspaceId
    name: str


@dataclass(frozen=True)
class AgentDefinitionVersion:
    definition: AgentDefinition
    version: Version
    role: str
    instructions: str
    allowed_actions: tuple[ActionType, ...]
    autonomy_ceiling: int = 1
    model_name: str = "scripted-v1"
    schema_version: int = 1
    allowed_tools: tuple[ToolGrant, ...] = ()
    knowledge_scope: KnowledgeScope = KnowledgeScope()
    memory_access: MemoryAccessPolicy = MemoryAccessPolicy()
    capabilities: tuple[str, ...] = ()
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.knowledge_scope, KnowledgeScope):
            raise InvariantViolation("knowledge_scope_type")
        if not isinstance(self.memory_access, MemoryAccessPolicy):
            raise InvariantViolation("memory_access_policy_type")
        if (
            not isinstance(self.capabilities, tuple)
            or len(self.capabilities) > 10
            or len(set(self.capabilities)) != len(self.capabilities)
            or any(
                not isinstance(capability, str)
                or not capability
                or len(capability) > 64
                or capability != capability.casefold()
                for capability in self.capabilities
            )
            or type(self.enabled) is not bool
        ):
            raise InvariantViolation("agent_capability_catalog")
        if (
            not isinstance(self.allowed_tools, tuple)
            or len(self.allowed_tools) > 3
            or any(not isinstance(grant, ToolGrant) for grant in self.allowed_tools)
            or len(set(grant.tool_id for grant in self.allowed_tools)) != len(self.allowed_tools)
        ):
            raise InvariantViolation("tool_grants_unique_exact_versions")
        for value in (self.definition.name, self.role, self.instructions, self.model_name):
            clean_required_text(value, "agent_configuration")
            if len(value) > 4000:
                raise InvariantViolation("agent_configuration_size")
        if self.autonomy_ceiling not in (0, 1, 2) or self.schema_version != 1:
            raise InvariantViolation("agent_configuration_policy")
        if not isinstance(self.allowed_actions, tuple) or any(
            not isinstance(action, ActionType) for action in self.allowed_actions
        ):
            raise InvariantViolation("agent_actions_typed")


@dataclass(frozen=True)
class RuntimeLimits:
    max_iterations: int = 5
    execution_seconds: int = 60
    model_seconds: int = 5
    recent_observations: int = 4
    max_context_chars: int = 16000
    max_response_chars: int = 8000
    max_tool_calls: int = 5
    max_calls_per_tool: int = 3

    def __post_init__(self) -> None:
        for value, maximum in (
            (self.max_iterations, 20),
            (self.execution_seconds, 600),
            (self.model_seconds, 60),
            (self.recent_observations, 20),
            (self.max_context_chars, 64000),
            (self.max_response_chars, 32000),
            (self.max_tool_calls, 20),
            (self.max_calls_per_tool, 20),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise InvariantViolation("runtime_limit_range")


@dataclass(frozen=True)
class Fact:
    key: str
    value: str
    source_id: str


@dataclass(frozen=True)
class SourceText:
    source_id: str
    text: str


@dataclass(frozen=True)
class SuppliedContext:
    workspace_id: WorkspaceId
    task_id: TaskId
    required_keys: tuple[str, ...]
    facts: tuple[Fact, ...]
    source_texts: tuple[SourceText, ...] = ()

    def __post_init__(self) -> None:
        if any(
            fact.source_id.startswith(("tool_receipt:", "knowledge:", "memory:"))
            for fact in self.facts
        ):
            raise InvariantViolation("supplied_sources_cannot_impersonate_tool_receipts")
        if any(
            s.source_id.startswith(("tool_receipt:", "knowledge:", "memory:"))
            for s in self.source_texts
        ):
            raise InvariantViolation("supplied_sources_cannot_impersonate_runtime_evidence")
        if not self.required_keys or len(set(self.required_keys)) != len(self.required_keys):
            raise InvariantViolation("required_fact_keys_unique_nonempty")
        if any(
            not isinstance(items, tuple) or len(items) > 50
            for items in (self.required_keys, self.facts, self.source_texts)
        ):
            raise InvariantViolation("context_collection_bound")
        values = list(self.required_keys)
        values.extend(
            value for fact in self.facts for value in (fact.key, fact.value, fact.source_id)
        )
        values.extend(
            value for source in self.source_texts for value in (source.source_id, source.text)
        )
        for value in values:
            if not isinstance(value, str) or not value.strip() or len(value) > 4000:
                raise InvariantViolation("context_field_bound")


class ObservationKind(StrEnum):
    TOOL_RESULT = "tool_result"
    CONTEXT_RECEIVED = "context_received"
    ACTION_ACCEPTED = "action_accepted"
    ACTION_REJECTED = "action_rejected"
    COMPLETION_RESULT = "completion_result"
    VALIDATION_ERROR = "validation_error"


@dataclass(frozen=True)
class Observation:
    id: ObservationId
    run_id: AgentRunId
    workspace_id: WorkspaceId
    kind: ObservationKind
    message: str
    action_id: ActionId | None = None
    provenance: str = "runtime"
    trust: str = "validated_runtime_metadata"
    schema_version: int = 1
    tool_result: ToolObservationData | None = None

    def __post_init__(self) -> None:
        if not self.message or len(self.message) > 1000 or self.schema_version != 1:
            raise InvariantViolation("observation_schema_and_size")
        if (self.kind is ObservationKind.TOOL_RESULT) != (self.tool_result is not None):
            raise InvariantViolation("tool_observation_payload")


@dataclass(frozen=True)
class ResearchBrief:
    summary: str
    findings: tuple[Fact, ...]
    gaps: tuple[str, ...]
    source_references: tuple[str, ...]


@dataclass(frozen=True)
class AgentWorkingState:
    iteration: int = 0
    observations: tuple[Observation, ...] = ()
    missing_fields: tuple[str, ...] = ()
    invocation_pending: bool = False
    active_evidence_pack_id: EvidencePackId | None = None
    active_memory_pack_id: MemoryContextPackId | None = None

    def __post_init__(self) -> None:
        if (
            type(self.iteration) is not int
            or self.iteration < 0
            or not isinstance(self.observations, tuple)
            or not isinstance(self.missing_fields, tuple)
        ):
            raise InvariantViolation("working_state_schema")


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class AgentRun:
    id: AgentRunId
    workspace_id: WorkspaceId
    execution_id: ExecutionId
    task_attempt_id: TaskAttemptId
    task_id: TaskId
    goal_id: GoalId
    definition_version: AgentDefinitionVersion
    limits: RuntimeLimits
    context: SuppliedContext
    created_at: datetime
    deadline: datetime
    version: Version = Version(1)
    status: AgentRunStatus = AgentRunStatus.RUNNING
    working_state: AgentWorkingState = AgentWorkingState()
    ended_at: datetime | None = None
    error_code: str | None = None
    result: ResearchBrief | None = None
    runtime_protocol: str = "single-agent-v1"
    policy_version: str = "internal-actions-v1"
    evaluator_version: str = "supplied-facts-v1"

    def __post_init__(self) -> None:
        require_utc(self.created_at, "created_at")
        require_utc(self.deadline, "deadline")
        if self.deadline <= self.created_at:
            raise InvariantViolation("deadline_after_start")
        if (
            self.context.workspace_id != self.workspace_id
            or self.context.task_id != self.task_id
            or self.definition_version.definition.workspace_id != self.workspace_id
        ):
            raise InvariantViolation("immutable_run_scope")
        terminal = self.status in {
            AgentRunStatus.SUCCEEDED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }
        if terminal != (self.ended_at is not None):
            raise InvariantViolation("terminal_run_end_time")
        if self.ended_at is not None:
            require_utc(self.ended_at, "ended_at")
            if self.ended_at < self.created_at:
                raise InvariantViolation("run_time_order")
        if (self.status is AgentRunStatus.SUCCEEDED) != (self.result is not None):
            raise InvariantViolation("succeeded_run_requires_result")
        if self.status in (AgentRunStatus.FAILED, AgentRunStatus.CANCELLED) and not self.error_code:
            raise InvariantViolation("terminal_failure_requires_reason")
        if (
            self.working_state.iteration > self.limits.max_iterations
            or len(self.working_state.observations) > self.limits.recent_observations
            or terminal
            and self.working_state.invocation_pending
        ):
            raise InvariantViolation("run_working_state_bounds")

    def evolve(
        self,
        *,
        at: datetime,
        status: AgentRunStatus | None = None,
        working_state: AgentWorkingState | None = None,
        context: SuppliedContext | None = None,
        error_code: str | None = None,
        result: ResearchBrief | None = None,
    ) -> "AgentRun":
        target = status or self.status
        allowed = {
            AgentRunStatus.RUNNING: set(AgentRunStatus),
            AgentRunStatus.WAITING: {
                AgentRunStatus.RUNNING,
                AgentRunStatus.FAILED,
                AgentRunStatus.CANCELLED,
            },
        }
        if target not in allowed.get(self.status, set()):
            raise InvalidStateTransition("AgentRun", str(self.id), self.status, target)
        state = working_state or self.working_state
        if context is not None and context.required_keys != self.context.required_keys:
            raise InvariantViolation("acceptance_contract_is_immutable")
        if (
            state.iteration < self.working_state.iteration
            or state.iteration > self.limits.max_iterations
            or len(state.observations) > self.limits.recent_observations
        ):
            raise InvariantViolation("working_state_bounds")
        terminal = target in {
            AgentRunStatus.SUCCEEDED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }
        return replace(
            self,
            status=target,
            version=self.version.next(),
            working_state=state,
            context=context or self.context,
            ended_at=at if terminal else None,
            error_code=error_code,
            result=result,
        )
