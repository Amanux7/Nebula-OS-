"""Explicit metadata projection over validated canonical records.

No record payloads, prompts, message bodies, source content, memory text, Tool input,
Tool output, free-text reviewer reasons or secrets are returned, even to admins.
"""

from dataclasses import is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.domain.errors import EntityNotFound, InvariantViolation
from agent_company_os.domain.ids import OpaqueId, Version, WorkspaceId
from agent_company_os.ports.inspection import InspectionRecord

# External category names do not accept table/column names supplied by the client.
COLLECTIONS = {
    "workspaces": "workspace",
    "goals": "goal",
    "tasks": "task",
    "attempts": "task_attempt",
    "executions": "execution",
    "runs": "runs",
    "agents": "definitions",
    "organization": "graphs",
    "graph_versions": "graph_versions",
    "orchestrations": "orchestrations",
    "plans": "plans",
    "delegations": "delegations",
    "messages": "messages",
    "threads": "threads",
    "handoffs": "handoffs",
    "knowledge": "sources",
    "knowledge_versions": "source_versions",
    "memory": "entries",
    "memory_candidates": "candidates",
    "approvals": "governance",
    "intents": "governance",
    "tools": "tool_registry",
    "invocations": "invocations",
    "receipts": "receipts",
}

# Fixed paths are the complete public contract. Adding a domain field does not expose it.
PATHS = (
    "id",
    "workspace_id",
    "name",
    "title",
    "objective",
    "status",
    "version",
    "created_at",
    "updated_at",
    "ended_at",
    "deadline",
    "expires_at",
    "enabled",
    "goal_id",
    "task_id",
    "execution_id",
    "task_attempt_id",
    "run_id",
    "agent_run_id",
    "orchestration_run_id",
    "plan_id",
    "plan_version",
    "delegation_id",
    "thread_id",
    "sender_id",
    "recipient_id",
    "source_id",
    "source_version",
    "active_version",
    "definition.id",
    "definition.name",
    "definition.role",
    "definition.workspace_id",
    "definition_version.definition.id",
    "definition_version.version",
    "autonomy_ceiling",
    "working_state.iteration",
    "working_state.invocation_pending",
    "working_state.active_evidence_pack_id",
    "working_state.active_memory_pack_id",
    "limits.max_iterations",
    "limits.max_tool_calls",
    "organization_snapshot.version",
    "graph_version",
    "replan_count",
    "retry_count",
    "redelegation_count",
    "failure_count",
    "intent.id",
    "intent.agent_run_id",
    "intent.action_id",
    "intent.fingerprint",
    "intent.risk",
    "intent.operation",
    "intent.effect",
    "intent.created_at",
    "intent.expires_at",
    "intent.policy.version",
    "intent.tool_version.definition.id",
    "intent.tool_version.version",
    "request.intent_id",
    "request.fingerprint",
    "request.expires_at",
    "consumed",
    "cancelled",
    "invocation_id",
    "invocation.id",
    "invocation.run_id",
    "invocation.action_id",
    "invocation.status",
    "invocation.outcome",
    "invocation.tool_version.definition.id",
    "invocation.tool_version.version",
    "tool_version.definition.id",
    "tool_version.definition.name",
    "tool_version.definition.risk",
    "tool_version.version",
    "outcome",
    "certainty",
    "risk",
    "kind",
    "revision",
)


def _value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (str, int, bool, OpaqueId)):
        return str(value)[:500]
    if isinstance(value, Version):
        return str(value.value)
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def project(record: Any, key: str, kind: str) -> InspectionRecord:
    fields: list[tuple[str, str]] = []
    for path in PATHS:
        value = record
        for component in path.split("."):
            value = getattr(value, component, None) if is_dataclass(value) else None
        text = _value(value)
        if text is not None:
            fields.append((path, text))
    # Structured decision metadata only. Reasons and preview are intentionally excluded.
    for i, decision in enumerate(getattr(record, "decisions", ())):
        for name in ("kind", "at", "reviewer", "policy_version", "fingerprint"):
            text = _value(getattr(decision, name, None))
            if text is not None:
                fields.append((f"decisions.{i}.{name}", text))
    return InspectionRecord(key, kind, tuple(fields))


class SqliteInspectionCatalog:
    def __init__(self, group: SqliteStoreGroup) -> None:
        self.group = group

    def records(self, workspace: WorkspaceId, kind: str) -> tuple[InspectionRecord, ...]:
        with self.group.transaction():
            self.group.domain.get_workspace(workspace)
            if kind == "departments":
                try:
                    graph = self.group.organization.graph(workspace)
                except EntityNotFound:
                    return ()
                if graph.active_version is None:
                    return ()
                version = self.group.organization.version(workspace, graph.active_version)
                return tuple(project(d, str(d.id), kind) for d in version.departments)
            collection = COLLECTIONS.get(kind)
            if collection is None:
                raise InvariantViolation("unknown_inspection_category")
            descriptor = self.group._domain.get(collection) or self.group._collections[collection]
            records = getattr(descriptor.owner, descriptor.attribute)
            result = []
            for key, record in records.items():
                if self.group._workspace(record) != workspace:
                    continue
                if isinstance(key, tuple):
                    identity = ":".join(_value(v) or "" for v in key)
                else:
                    simple = _value(key)
                    identity = (
                        simple if simple is not None else f"{key.tool_id}:{key.version.value}"
                    )
                result.append(project(record, identity, kind))
            return tuple(sorted(result, key=lambda record: record.id))
