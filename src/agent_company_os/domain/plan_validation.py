"""Pure validation for untrusted orchestration plan proposals."""

from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.orchestration import (
    AgentCatalogItem,
    AgentRequirements,
    OrchestrationRequest,
    PlanProposal,
)


def _eligible(requirements: AgentRequirements, agent: AgentCatalogItem) -> bool:
    return (
        set(requirements.capabilities) <= set(agent.capabilities)
        and set(requirements.tool_ids) <= set(agent.tool_ids)
        and set(requirements.knowledge_source_ids) <= set(agent.knowledge_source_ids)
        and set(requirements.memory_scopes) <= set(agent.memory_scopes)
        and requirements.min_autonomy <= agent.autonomy_ceiling
    )


def validate_plan(request: OrchestrationRequest, proposal: PlanProposal) -> None:
    policy = request.policy
    if proposal.workspace_id != request.workspace_id or proposal.goal_id != request.goal_id:
        raise InvariantViolation("plan_workspace_or_goal")
    if not proposal.tasks or len(proposal.tasks) > policy.max_tasks:
        raise InvariantViolation("plan_task_count")
    ids = [task.id for task in proposal.tasks]
    if len(ids) != len(set(ids)):
        raise InvariantViolation("plan_duplicate_task_id")
    known = set(ids)
    text_size = 0
    graph: dict[str, tuple[str, ...]] = {}
    for task in proposal.tasks:
        if len(task.dependencies) > policy.max_dependencies_per_task:
            raise InvariantViolation("plan_dependency_count")
        if not set(task.dependencies) <= known or task.id in task.dependencies:
            raise InvariantViolation("plan_unknown_or_self_dependency")
        if not any(_eligible(task.requirements, agent) for agent in request.agents):
            raise InvariantViolation("plan_no_eligible_agent_requirement")
        graph[task.id] = task.dependencies
        text_size += len(task.id) + len(task.title) + sum(map(len, task.acceptance_criteria))
    if text_size > policy.max_plan_text:
        raise InvariantViolation("plan_text_limit")

    visiting: set[str] = set()
    depths: dict[str, int] = {}

    def visit(node: str) -> int:
        if node in visiting:
            raise InvariantViolation("plan_cycle")
        if node in depths:
            return depths[node]
        visiting.add(node)
        depth = 1 + max((visit(parent) for parent in graph[node]), default=0)
        visiting.remove(node)
        depths[node] = depth
        if depth > policy.max_dependency_depth:
            raise InvariantViolation("plan_dependency_depth")
        return depth

    for task_id in ids:
        visit(task_id)
