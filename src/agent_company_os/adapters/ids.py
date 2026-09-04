"""Random production IDs and predictable test IDs."""

from collections import defaultdict
from uuid import uuid4

from agent_company_os.domain.agent import ActionId, AgentRunId, ObservationId
from agent_company_os.domain.ids import (
    EventId,
    ExecutionId,
    GoalId,
    StateTransitionId,
    TaskAttemptId,
    TaskId,
    WorkspaceId,
)
from agent_company_os.domain.knowledge import EvidencePackId, KnowledgeSourceId
from agent_company_os.domain.memory import MemoryCandidateId, MemoryContextPackId, MemoryEntryId
from agent_company_os.domain.orchestration import (
    DelegationId,
    OrchestrationPlanId,
    OrchestrationRunId,
)
from agent_company_os.domain.tools import ToolInvocationId, ToolReceiptId


class SystemIdGenerator:
    def orchestration_run_id(self) -> OrchestrationRunId:
        return OrchestrationRunId(str(uuid4()))

    def orchestration_plan_id(self) -> OrchestrationPlanId:
        return OrchestrationPlanId(str(uuid4()))

    def delegation_id(self) -> DelegationId:
        return DelegationId(str(uuid4()))

    def memory_candidate_id(self) -> MemoryCandidateId:
        return MemoryCandidateId(str(uuid4()))

    def memory_entry_id(self) -> MemoryEntryId:
        return MemoryEntryId(str(uuid4()))

    def memory_context_pack_id(self) -> MemoryContextPackId:
        return MemoryContextPackId(str(uuid4()))

    def knowledge_source_id(self) -> KnowledgeSourceId:
        return KnowledgeSourceId(str(uuid4()))

    def evidence_pack_id(self) -> EvidencePackId:
        return EvidencePackId(str(uuid4()))

    def tool_invocation_id(self) -> ToolInvocationId:
        return ToolInvocationId(str(uuid4()))

    def tool_receipt_id(self) -> ToolReceiptId:
        return ToolReceiptId(str(uuid4()))

    def agent_run_id(self) -> AgentRunId:
        return AgentRunId(str(uuid4()))

    def action_id(self) -> ActionId:
        return ActionId(str(uuid4()))

    def observation_id(self) -> ObservationId:
        return ObservationId(str(uuid4()))

    def workspace_id(self) -> WorkspaceId:
        return WorkspaceId(str(uuid4()))

    def goal_id(self) -> GoalId:
        return GoalId(str(uuid4()))

    def task_id(self) -> TaskId:
        return TaskId(str(uuid4()))

    def task_attempt_id(self) -> TaskAttemptId:
        return TaskAttemptId(str(uuid4()))

    def execution_id(self) -> ExecutionId:
        return ExecutionId(str(uuid4()))

    def event_id(self) -> EventId:
        return EventId(str(uuid4()))

    def state_transition_id(self) -> StateTransitionId:
        return StateTransitionId(str(uuid4()))


class DeterministicIdGenerator:
    def orchestration_run_id(self) -> OrchestrationRunId:
        return OrchestrationRunId(self._next("orchestration-run"))

    def orchestration_plan_id(self) -> OrchestrationPlanId:
        return OrchestrationPlanId(self._next("orchestration-plan"))

    def delegation_id(self) -> DelegationId:
        return DelegationId(self._next("delegation"))

    def memory_candidate_id(self) -> MemoryCandidateId:
        return MemoryCandidateId(self._next("memory-candidate"))

    def memory_entry_id(self) -> MemoryEntryId:
        return MemoryEntryId(self._next("memory-entry"))

    def memory_context_pack_id(self) -> MemoryContextPackId:
        return MemoryContextPackId(self._next("memory-pack"))

    def knowledge_source_id(self) -> KnowledgeSourceId:
        return KnowledgeSourceId(self._next("knowledge-source"))

    def evidence_pack_id(self) -> EvidencePackId:
        return EvidencePackId(self._next("evidence-pack"))

    def tool_invocation_id(self) -> ToolInvocationId:
        return ToolInvocationId(self._next("tool-invocation"))

    def tool_receipt_id(self) -> ToolReceiptId:
        return ToolReceiptId(self._next("tool-receipt"))

    def agent_run_id(self) -> AgentRunId:
        return AgentRunId(self._next("agent-run"))

    def action_id(self) -> ActionId:
        return ActionId(self._next("action"))

    def observation_id(self) -> ObservationId:
        return ObservationId(self._next("observation"))

    def __init__(self, prefix: str = "test") -> None:
        self._prefix = prefix
        self._counts: defaultdict[str, int] = defaultdict(int)

    def _next(self, kind: str) -> str:
        self._counts[kind] += 1
        return f"{self._prefix}-{kind}-{self._counts[kind]:04d}"

    def workspace_id(self) -> WorkspaceId:
        return WorkspaceId(self._next("workspace"))

    def goal_id(self) -> GoalId:
        return GoalId(self._next("goal"))

    def task_id(self) -> TaskId:
        return TaskId(self._next("task"))

    def task_attempt_id(self) -> TaskAttemptId:
        return TaskAttemptId(self._next("attempt"))

    def execution_id(self) -> ExecutionId:
        return ExecutionId(self._next("execution"))

    def event_id(self) -> EventId:
        return EventId(self._next("event"))

    def state_transition_id(self) -> StateTransitionId:
        return StateTransitionId(self._next("transition"))
