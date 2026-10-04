"""Explicit metadata projection over validated canonical records.

No record payloads, prompts, message bodies, source content, memory text, Tool input,
Tool output, free-text reviewer reasons or secrets are returned, even to admins.
"""

from dataclasses import is_dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Any, cast

from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.domain.errors import EntityNotFound, InvariantViolation
from agent_company_os.domain.ids import OpaqueId, Version, WorkspaceId
from agent_company_os.ports.inspection import InspectionLink, InspectionRecord

# External category names do not accept table/column names supplied by the client.
COLLECTIONS = {
    "workspaces": "workspace",
    "goals": "goal",
    "tasks": "task",
    "attempts": "task_attempt",
    "executions": "execution",
    "runs": "runs",
    "agents": "definitions",
    "agent_versions": "definitions",
    "organization": "graphs",
    "graph_versions": "graph_versions",
    "orchestrations": "orchestrations",
    "plans": "plans",
    "materializations": "materializations",
    "delegations": "delegations",
    "delegation_attempts": "delegation_attempts",
    "results": "runs",
    "messages": "messages",
    "threads": "threads",
    "handoffs": "handoffs",
    "knowledge": "sources",
    "knowledge_versions": "source_versions",
    "memory": "entries",
    "memory_candidates": "candidates",
    "approvals": "governance",
    "approval_requests": "governance",
    "approval_decisions": "governance",
    "intents": "governance",
    "tools": "tool_registry",
    "tool_versions": "tool_registry",
    "invocations": "invocations",
    "receipts": "receipts",
}

# Fixed paths are the complete public contract. Adding a domain field does not expose it.
PATHS = (
    "role",
    "description",
    "started_at",
    "materialized_at",
    "current_plan_version",
    "organization.version",
    "organization_version",
    "policy.version",
    "strategy_id",
    "strategy_version",
    "agent_run_count",
    "failed_attempt_count",
    "agent_definition_id",
    "agent_definition_version",
    "planned_task_id",
    "retry_ordinal",
    "redelegation_ordinal",
    "error_code",
    "request_fingerprint",
    "executor_kind",
    "tool_version.executor_kind",
    "invocation.started_at",
    "invocation.ended_at",
    "invocation.error_code",
    "invocation.request_fingerprint",
    "invocation.execution_id",
    "invocation.task_attempt_id",
    "invocation.tool_version.definition.risk",
    "invocation.tool_version.executor_kind",
    "remote_outcome",
    "input_bytes",
    "output_bytes",
    "intent.run_id",
    "intent.goal_id",
    "intent.task_id",
    "intent.execution_id",
    "intent.tool.definition.id",
    "intent.tool.definition.risk",
    "intent.tool.executor_kind",
    "intent.tool.version",
    "intent_id",
    "fingerprint",
    "policy_version",
    "at",
    "reviewer.id",
    "sender_agent_run_id",
    "recipient_agent_run_id",
    "sender_definition_id",
    "sender_definition_version",
    "recipient_definition_id",
    "recipient_definition_version",
    "sender_task_id",
    "recipient_task_id",
    "sender_delegation_id",
    "recipient_delegation_id",
    "source_task_id",
    "source_delegation_id",
    "resulting_delegation_id",
    "parent_handoff_id",
    "correlation_id",
    "delivered_at",
    "depth",
    "result_reference",
    "created_by",
    "source.id",
    "source.title",
    "trust_class",
    "source_type",
    "content_digest",
    "trust",
    "content_version",
    "source.name",
    "source.trust",
    "source.content_version",
    "content_hash",
    "chunking_algorithm",
    "graph_id",
    "memory_type",
    "scope.kind",
    "sensitivity",
    "reviewed_by",
    "reviewed_at",
    "candidate.id",
    "candidate.status",
    "candidate.policy_version",
    "candidate.provenance.kind",
    "candidate.provenance.run_id",
    "candidate.provenance.authority",
    "provenance.kind",
    "provenance.run_id",
    "provenance.authority",
    "supersedes_id",
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
        for name in ("kind", "at", "policy_version", "fingerprint"):
            text = _value(getattr(decision, name, None))
            if text is not None:
                fields.append((f"decisions.{i}.{name}", text))
        if decision.reviewer is not None:
            fields.append((f"decisions.{i}.reviewer_id", str(decision.reviewer.id)))
    references = getattr(record, "references", ())
    if references:
        fields.append(("reference_types", ", ".join(sorted({r.kind.value for r in references}))))
    return InspectionRecord(key, kind, tuple(fields))


LINK_FIELDS = {
    "definition.id": "agents",
    "tool_version.definition.id": "tools",
    "workspace_id": "workspaces",
    "goal_id": "goals",
    "task_id": "tasks",
    "execution_id": "executions",
    "task_attempt_id": "attempts",
    "run_id": "runs",
    "agent_run_id": "runs",
    "orchestration_run_id": "orchestrations",
    "delegation_id": "delegations",
    "thread_id": "threads",
    "invocation_id": "invocations",
    "sender_agent_run_id": "runs",
    "recipient_agent_run_id": "runs",
    "sender_task_id": "tasks",
    "recipient_task_id": "tasks",
    "source_task_id": "tasks",
    "sender_delegation_id": "delegations",
    "recipient_delegation_id": "delegations",
    "source_delegation_id": "delegations",
    "resulting_delegation_id": "delegations",
    "parent_handoff_id": "handoffs",
    "intent_id": "intents",
    "created_by": "runs",
    "intent.id": "intents",
    "intent.run_id": "runs",
    "intent.goal_id": "goals",
    "intent.task_id": "tasks",
    "intent.execution_id": "executions",
    "invocation.id": "invocations",
    "invocation.run_id": "runs",
    "invocation.execution_id": "executions",
    "invocation.task_attempt_id": "attempts",
    "request.intent_id": "intents",
    "source.id": "knowledge",
    "source_id": "knowledge",
    "candidate.id": "memory_candidates",
    "candidate.provenance.run_id": "runs",
    "provenance.run_id": "runs",
    "supersedes_id": "memory",
}


def linked(record: InspectionRecord) -> InspectionRecord:
    fields = dict(record.fields)
    links = [
        InspectionLink(key, category, fields[key])
        for key, category in LINK_FIELDS.items()
        if key in fields and (category, fields[key]) != (record.kind, record.id)
    ]
    for identity, version, category in (
        ("definition_version.definition.id", "definition_version.version", "agent_versions"),
        ("agent_definition_id", "agent_definition_version", "agent_versions"),
        ("sender_definition_id", "sender_definition_version", "agent_versions"),
        ("recipient_definition_id", "recipient_definition_version", "agent_versions"),
        ("plan_id", "plan_version", "plans"),
        ("plan_id", "current_plan_version", "plans"),
        ("tool_version.definition.id", "tool_version.version", "tool_versions"),
        (
            "invocation.tool_version.definition.id",
            "invocation.tool_version.version",
            "tool_versions",
        ),
        ("intent.tool.definition.id", "intent.tool.version", "tool_versions"),
    ):
        if identity in fields and version in fields:
            links.append(
                InspectionLink(category, category, f"{fields[identity]}:{fields[version]}")
            )
    return replace(record, links=tuple(links))


class SqliteInspectionCatalog:
    def __init__(self, group: SqliteStoreGroup) -> None:
        self.group = group

    def _spatial_metadata(
        self, workspace: WorkspaceId, kind: str, record: Any
    ) -> tuple[list[tuple[str, str]], list[InspectionLink]]:
        """Explicit IDs and classifications for spatial views, never content or authority."""
        fields: list[tuple[str, str]] = []
        links: list[InspectionLink] = []

        def add(path: str, value: object, category: str | None = None) -> None:
            text = _value(value)
            if text is not None:
                fields.append((path, text))
                if category is not None:
                    links.append(InspectionLink(path, category, text))

        if kind in ("organization", "graph_versions"):
            graph_version = record
            if kind == "organization":
                graph_version = (
                    self.group.organization.version(workspace, record.active_version)
                    if record.active_version is not None
                    else None
                )
            if graph_version is not None:
                add("membership_count", len(graph_version.memberships))
                for i, membership in enumerate(graph_version.memberships):
                    prefix = f"membership.{i}"
                    add(f"{prefix}.agent_definition_id", membership.agent_id, "agents")
                    add(f"{prefix}.department_id", membership.department_id, "departments")
                    add(f"{prefix}.status", membership.status)
                    add(f"{prefix}.discoverable", membership.discoverable)
                    add(f"{prefix}.effective_from", membership.effective_from)
                    add(f"{prefix}.effective_until", membership.effective_until)
        if kind == "tasks":
            # Replans can retain a Task ID. Use the latest materialized version and expose
            # its exact plan identity rather than guessing dependencies from titles.
            materializations = [
                m
                for m in self.group.orchestration._materializations.values()
                if m.workspace_id == workspace and any(t.task_id == record.id for t in m.tasks)
            ]
            if materializations:
                materialization = max(
                    materializations, key=lambda m: (m.materialized_at, m.plan_version.value)
                )
                plan = self.group.orchestration.plan(
                    workspace, materialization.plan_id, materialization.plan_version
                )
                identities = {t.planned_task_id: t.task_id for t in materialization.tasks}
                planned_id = next(
                    t.planned_task_id for t in materialization.tasks if t.task_id == record.id
                )
                planned = next(t for t in plan.proposal.tasks if t.id == planned_id)
                add("planned_task_id", planned_id)
                add("plan_id", materialization.plan_id)
                add("plan_version", materialization.plan_version)
                add("dependency_count", len(planned.dependencies))
                for i, dependency in enumerate(planned.dependencies):
                    add(f"dependency.{i}.task_id", identities[dependency], "tasks")
        if kind == "knowledge_versions":
            chunks = self.group.knowledge.chunks(
                workspace, record.source.id, record.source.content_version
            )
            add("chunk_count", len(chunks))
            for i, chunk in enumerate(chunks):
                add(f"chunk.{i}.id", chunk.id)
                add(f"chunk.{i}.source_id", chunk.source_id, "knowledge")
                add(f"chunk.{i}.source_version", chunk.source_version)
                add(f"chunk.{i}.ordinal", chunk.ordinal)
        if kind in ("runs", "results"):
            packs = self.group.knowledge.packs(workspace, record.id)
            add("evidence_pack_count", len(packs))
            for i, pack in enumerate(packs):
                prefix = f"evidence.{i}"
                add(f"{prefix}.pack_id", pack.id)
                add(f"{prefix}.created_at", pack.created_at)
                add(f"{prefix}.candidate_count", pack.result.candidate_count)
                add(f"{prefix}.returned_count", len(pack.result.candidates))
                for j, candidate in enumerate(pack.result.candidates):
                    source = f"{prefix}.source.{j}"
                    chunk = candidate.chunk
                    add(f"{source}.source_id", chunk.source_id, "knowledge")
                    add(f"{source}.source_version", chunk.source_version)
                    add(f"{source}.chunk_id", chunk.id)
                    add(f"{source}.trust", candidate.trust)
                    links.append(
                        InspectionLink(
                            f"{source}.version",
                            "knowledge_versions",
                            f"{chunk.source_id}:{chunk.source_version.value}",
                        )
                    )
            memory_packs = self.group.memory.packs(workspace, record.id)
            add("memory_pack_count", len(memory_packs))
            for i, memory_pack in enumerate(memory_packs):
                prefix = f"memory_pack.{i}"
                add(f"{prefix}.id", memory_pack.id)
                add(f"{prefix}.created_at", memory_pack.created_at)
                add(f"{prefix}.hit_count", len(memory_pack.result.hits))
                for j, hit in enumerate(memory_pack.result.hits):
                    entry = f"{prefix}.entry.{j}"
                    add(f"{entry}.id", hit.entry.id, "memory")
                    add(f"{entry}.version", hit.entry.version)
                    add(f"{entry}.authority", hit.entry.candidate.provenance.authority)
                    add(f"{entry}.conflicts_with_knowledge", hit.conflicts_with_knowledge)
                    add(f"{entry}.conflicting_entry_count", len(hit.conflicting_entry_ids))
        if kind == "memory_candidates":
            add("provenance.reference_count", len(record.provenance.source_references))
        elif kind == "memory":
            add("provenance.reference_count", len(record.candidate.provenance.source_references))
        return fields, links

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
                return tuple(linked(project(d, str(d.id), kind)) for d in version.departments)
            collection = COLLECTIONS.get(kind)
            if collection is None:
                raise InvariantViolation("unknown_inspection_category")
            descriptor = self.group._domain.get(collection) or self.group._collections[collection]
            records = getattr(descriptor.owner, descriptor.attribute)
            result: list[InspectionRecord] = []
            entries = enumerate(records) if descriptor.sequence else records.items()
            for key, record in entries:
                if self.group._workspace(record) != workspace:
                    continue
                if kind == "results" and record.result is None:
                    continue
                if isinstance(key, tuple):
                    identity = ":".join(_value(v) or "" for v in key)
                else:
                    simple = _value(key)
                    identity = (
                        simple
                        if simple is not None
                        else f"{cast(Any, key).tool_id}:{cast(Any, key).version.value}"
                    )
                if kind == "agents":
                    record, identity = record.definition, str(record.definition.id)
                elif kind == "tools":
                    record = record.tool_version.definition
                    identity = str(record.id)
                elif kind == "approval_requests":
                    if record.request is None:
                        continue
                    record, identity = record.request, str(record.intent.id)
                elif kind == "approval_decisions":
                    result.extend(
                        linked(project(d, f"{record.intent.id}:{i}", kind))
                        for i, d in enumerate(record.decisions)
                    )
                    continue
                projected = project(record, identity, kind)
                extra, spatial_links = self._spatial_metadata(workspace, kind, record)
                if kind in ("runs", "results"):
                    extra += [
                        (
                            "tool_call_count",
                            str(len(self.group.runtime.tool_invocations(workspace, record.id))),
                        ),
                        ("observation_count", str(len(record.working_state.observations))),
                        ("result_available", str(record.result is not None)),
                    ]
                    if record.result is not None:
                        extra.append(("finding_count", str(len(record.result.findings))))
                    for attempt in self.group.orchestration._attempts:
                        if attempt.agent_run_id == record.id:
                            delegation = self.group.orchestration._delegations[
                                attempt.delegation_id
                            ]
                            extra += [
                                ("delegation_id", str(delegation.id)),
                                ("orchestration_run_id", str(delegation.orchestration_run_id)),
                            ]
                if kind == "results":
                    extra += [
                        ("agent_run_id", str(record.id)),
                        ("result_version", str(record.version.value)),
                        (
                            "reference",
                            f"task_result:{record.task_id}:{record.task_attempt_id}:{record.id}:v{record.version.value}",
                        ),
                    ]
                if kind in ("intents", "approvals"):
                    extra.append(
                        (
                            "restore_hold",
                            str(self.group.runtime.intent_held(workspace, record.intent.id)),
                        )
                    )
                if kind in ("invocations", "receipts"):
                    invocation = record if kind == "invocations" else record.invocation
                    receipt = next(
                        (
                            r
                            for r in self.group.runtime._tool_receipts.values()
                            if r.invocation.id == invocation.id
                        ),
                        None,
                    )
                    extra.append(
                        (
                            "outcome_certainty",
                            "outcome_unknown"
                            if receipt is None or receipt.remote_outcome == "unknown"
                            else "observed_success"
                            if receipt.output
                            else "observed_failure",
                        )
                    )
                    if receipt is not None:
                        extra.append(("receipt_id", str(receipt.id)))
                    for governed in self.group.runtime.governed_actions(workspace):
                        if governed.intent.action_id == invocation.action_id:
                            extra.append(("intent_id", str(governed.intent.id)))
                if kind == "materializations":
                    extra.extend((f"task.{i}", str(t.task_id)) for i, t in enumerate(record.tasks))
                projected = linked(replace(projected, fields=projected.fields + tuple(extra)))
                more = [*projected.links, *spatial_links]
                for name, value in extra:
                    if name.startswith("task."):
                        more.append(InspectionLink(name, "tasks", value))
                    elif name == "receipt_id":
                        more.append(InspectionLink(name, "receipts", value))
                result.append(replace(projected, links=tuple(more)))
            return tuple(sorted({r.id: r for r in result}.values(), key=lambda record: record.id))
