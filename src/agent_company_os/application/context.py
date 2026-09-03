"""Deterministic context bounding and low-risk action policy."""

from agent_company_os.domain.agent import ActionType, AgentRun
from agent_company_os.domain.decisions import ModelDecision, ModelFailure
from agent_company_os.domain.goal import Goal
from agent_company_os.domain.knowledge import EvidencePack
from agent_company_os.domain.task import Task
from agent_company_os.domain.tools import ToolVersion
from agent_company_os.ports.model import AgentModelRequest


class ContextAssembler:
    def assemble(
        self,
        run: AgentRun,
        goal: Goal,
        task: Task,
        tools: tuple[ToolVersion, ...] = (),
        knowledge: EvidencePack | None = None,
    ) -> AgentModelRequest:
        values = [
            goal.objective,
            task.title,
            *goal.constraints,
            *task.acceptance_criteria,
            run.definition_version.instructions,
            run.definition_version.role,
        ]
        values.extend(run.context.required_keys)
        values.extend(
            value for fact in run.context.facts for value in (fact.key, fact.value, fact.source_id)
        )
        values.extend(source.text + source.source_id for source in run.context.source_texts)
        values.extend(observation.message for observation in run.working_state.observations)
        for observation in run.working_state.observations:
            if observation.tool_result is not None:
                data = observation.tool_result
                values.extend((data.notes, str(data.tool_id), str(data.receipt_id)))
                values.extend(
                    value for fact in data.facts for value in (fact.key, fact.value, fact.source_id)
                )
        for tool in tools:
            values.extend(
                (
                    tool.definition.name,
                    tool.definition.description,
                    tool.input_schema,
                    tool.output_schema,
                    str(tool.definition.id),
                )
            )
        if (
            sum(len(value) for value in values) + (knowledge.context_chars if knowledge else 0)
            > run.limits.max_context_chars
        ):
            raise ModelFailure("context_overflow")
        return AgentModelRequest(
            run.definition_version,
            goal.objective,
            task.title,
            task.acceptance_criteria,
            goal.constraints,
            run.context,
            run.working_state.observations,
            run.definition_version.allowed_actions,
            run.working_state.iteration,
            run.limits.max_iterations,
            available_tools=tools,
            knowledge_evidence=knowledge,
        )


class ActionPolicy:
    version = "internal-actions-v1"

    @staticmethod
    def version_for(run: AgentRun) -> str:
        if run.definition_version.knowledge_scope.source_ids:
            return "bounded-knowledge-tools-v1"
        return (
            "read-only-tools-v1"
            if ActionType.CALL_TOOL in run.definition_version.allowed_actions
            else "internal-actions-v1"
        )

    def authorize(self, run: AgentRun, decision: ModelDecision) -> None:
        if decision.action_type not in run.definition_version.allowed_actions:
            raise ModelFailure("unauthorized_action")
        if (
            decision.action_type is ActionType.COMPLETE_TASK
            and run.definition_version.autonomy_ceiling < 1
        ):
            raise ModelFailure("autonomy_denied")
