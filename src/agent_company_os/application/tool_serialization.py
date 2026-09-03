"""Explicit bounded receipt export for audits; not an import or replay API."""

import json

from agent_company_os.application.tool_validation import input_json
from agent_company_os.domain.tools import ToolReceipt


def serialize_receipt(receipt: ToolReceipt) -> dict[str, object]:
    invocation = receipt.invocation
    version = invocation.tool_version
    output = receipt.output
    return {
        "schema_version": receipt.schema_version,
        "id": str(receipt.id),
        "invocation_id": str(invocation.id),
        "workspace_id": str(invocation.workspace_id),
        "agent_run_id": str(invocation.run_id),
        "execution_id": str(invocation.execution_id),
        "task_attempt_id": str(invocation.task_attempt_id),
        "action_id": str(invocation.action_id),
        "tool_id": str(version.definition.id),
        "tool_version": version.version.value,
        "tool_contract": {
            "name": version.definition.name,
            "description": version.definition.description,
            "risk": version.definition.risk.value,
            "executor_kind": version.executor_kind.value,
            "input_schema": version.input_schema,
            "output_schema": version.output_schema,
            "timeout_seconds": version.timeout_seconds,
            "max_input_bytes": version.max_input_bytes,
            "max_output_bytes": version.max_output_bytes,
            "max_retries": version.retry_policy.max_retries,
            "trust": version.trust,
        },
        "validated_input": json.loads(input_json(invocation.validated_input)),
        "request_fingerprint": invocation.request_fingerprint,
        "started_at": invocation.started_at.isoformat(),
        "ended_at": invocation.ended_at.isoformat() if invocation.ended_at else None,
        "invocation_version": invocation.version.value,
        "claimed_run_version": invocation.run_version.value,
        "parent_versions": [v.value for v in invocation.parent_versions],
        "registry_revision": invocation.registry_revision,
        "status": invocation.status.value,
        "error_code": invocation.error_code.value if invocation.error_code else None,
        "remote_outcome": receipt.remote_outcome,
        "input_bytes": receipt.input_bytes,
        "output_bytes": receipt.output_bytes,
        "output": {
            "subject": output.subject,
            "facts": [
                {"key": f.key, "value": f.value, "source_id": f.source_id} for f in output.facts
            ],
            "notes": output.notes,
        }
        if output
        else None,
    }
