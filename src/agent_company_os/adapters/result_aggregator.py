"""Deterministic structural result aggregation; it does not decide truth."""

from agent_company_os.domain.ids import GoalId
from agent_company_os.domain.orchestration import GoalResultDraft, TaskResultReference


class DeterministicResultAggregator:
    def aggregate(
        self,
        goal_id: GoalId,
        required_count: int,
        results: tuple[TaskResultReference, ...],
    ) -> GoalResultDraft:
        return GoalResultDraft(goal_id, results, len(results) == required_count)
