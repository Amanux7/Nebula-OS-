"""Least-privilege deterministic AgentDefinitionVersion selection."""

from agent_company_os.domain.agent import AgentDefinitionVersion, AgentRunStatus
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.ids import WorkspaceId
from agent_company_os.domain.orchestration import AgentRequirements
from agent_company_os.ports.runtime_store import RuntimeStore


class DeterministicAgentSelector:
    def __init__(self, runtime: RuntimeStore) -> None:
        self.runtime = runtime

    def select(
        self,
        workspace_id: WorkspaceId,
        requirements: AgentRequirements,
        candidates: tuple[AgentDefinitionVersion, ...],
        excluded: tuple[AgentDefinitionVersion, ...] = (),
    ) -> AgentDefinitionVersion:
        excluded_keys = {(item.definition.id, item.version) for item in excluded}
        eligible = []
        for item in candidates:
            if (
                item.definition.workspace_id != workspace_id
                or not item.enabled
                or (item.definition.id, item.version) in excluded_keys
                or not set(requirements.capabilities) <= set(item.capabilities)
                or not set(requirements.tool_ids) <= {grant.tool_id for grant in item.allowed_tools}
                or not set(requirements.knowledge_source_ids)
                <= set(item.knowledge_scope.source_ids)
                or not set(requirements.memory_scopes) <= set(item.memory_access.scopes)
                or item.autonomy_ceiling < requirements.min_autonomy
            ):
                continue
            canonical = self.runtime.definition(workspace_id, item.definition.id, item.version)
            if canonical == item:
                active = sum(
                    run.definition_version == item
                    and run.status in {AgentRunStatus.RUNNING, AgentRunStatus.WAITING}
                    for run in self.runtime.for_definition(item.definition.id)
                )
                eligible.append((active, str(item.definition.id), -item.version.value, item))
        if not eligible:
            raise InvariantViolation("no_eligible_agent")
        eligible.sort(key=lambda candidate: candidate[:3])
        return eligible[0][3]
