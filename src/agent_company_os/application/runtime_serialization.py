"""Explicit public result representation; no provider payload or private reasoning."""

from agent_company_os.domain.agent import AgentRun


def serialize_run(run: AgentRun) -> dict[str, object]:
    result: dict[str, object] | None = None
    if run.result is not None:
        result = {
            "summary": run.result.summary,
            "findings": [
                {"key": fact.key, "value": fact.value, "source_id": fact.source_id}
                for fact in run.result.findings
            ],
            "gaps": list(run.result.gaps),
            "source_references": list(run.result.source_references),
        }
    return {
        "schema_version": 1,
        "id": str(run.id),
        "workspace_id": str(run.workspace_id),
        "execution_id": str(run.execution_id),
        "task_id": str(run.task_id),
        "task_attempt_id": str(run.task_attempt_id),
        "agent_definition_id": str(run.definition_version.definition.id),
        "agent_definition_version": run.definition_version.version.value,
        "model_name": run.definition_version.model_name,
        "policy_version": run.policy_version,
        "runtime_protocol": run.runtime_protocol,
        "evaluator_version": run.evaluator_version,
        "version": run.version.value,
        "status": run.status.value,
        "started_at": run.created_at.isoformat(),
        "deadline": run.deadline.isoformat(),
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "iteration": run.working_state.iteration,
        "error_code": run.error_code,
        "missing_fields": list(run.working_state.missing_fields),
        "result": result,
    }
