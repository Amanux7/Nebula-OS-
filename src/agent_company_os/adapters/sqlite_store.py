"""SQLite adapters reusing the existing validated store contracts.

Each public store operation enters one shared unit of work. At its outer edge we
load current typed rows, apply existing guards, and persist a per-record CAS delta.
Nested operations share the connection; no executor object is serialized. This
bounded full-read adapter favors verifiable semantics over large-corpus throughput.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, fields, is_dataclass, replace
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import Any

from agent_company_os.adapters.communication_store import InMemoryCommunicationStore
from agent_company_os.adapters.durable_codec import (
    decode_record,
    decode_value,
    encode_record,
    encode_value,
)
from agent_company_os.adapters.in_memory import InMemoryDomainStore
from agent_company_os.adapters.knowledge_store import InMemoryKnowledgeStore
from agent_company_os.adapters.memory_store import InMemoryMemoryStore
from agent_company_os.adapters.orchestration_store import InMemoryOrchestrationStore
from agent_company_os.adapters.organization_store import InMemoryOrganizationStore
from agent_company_os.adapters.runtime_store import InMemoryRuntimeStore
from agent_company_os.adapters.sqlite_database import open_database
from agent_company_os.domain import agent as a
from agent_company_os.domain import communication as c
from agent_company_os.domain import governance as g
from agent_company_os.domain import knowledge as k
from agent_company_os.domain import memory as m
from agent_company_os.domain import orchestration as o
from agent_company_os.domain import organization as org
from agent_company_os.domain import tools as t
from agent_company_os.domain.decisions import Action
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.events import Event
from agent_company_os.domain.execution import Execution
from agent_company_os.domain.goal import Goal
from agent_company_os.domain.ids import (
    ExecutionId,
    GoalId,
    OpaqueId,
    TaskAttemptId,
    TaskId,
    Version,
    WorkspaceId,
)
from agent_company_os.domain.task import Task
from agent_company_os.domain.task_attempt import TaskAttempt
from agent_company_os.domain.transitions import StateTransition
from agent_company_os.domain.workspace import Workspace
from agent_company_os.ports.tools import ResolvedTool, ToolExecutor


def _scoped_operations(cls: type[Any]) -> type[Any]:
    """Wrap inherited port methods, not private validators or context managers."""

    def wrap(method: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(method)
        def call(self: Any, *args: Any, **kwargs: Any) -> Any:
            with self._durable.transaction():
                return method(self, *args, **kwargs)

        return call

    for name in dir(cls):
        if name.startswith("_") or name in {"atomic", "transaction"}:
            continue
        method = getattr(cls, name)
        if callable(method):
            setattr(cls, name, wrap(method))
    return cls


@_scoped_operations
class SqliteDomainStore(InMemoryDomainStore):
    _durable: SqliteStoreGroup

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._durable.transaction():
            yield


@_scoped_operations
class SqliteRuntimeStore(InMemoryRuntimeStore):
    _durable: SqliteStoreGroup


@_scoped_operations
class SqliteKnowledgeStore(InMemoryKnowledgeStore):
    _durable: SqliteStoreGroup


@_scoped_operations
class SqliteMemoryStore(InMemoryMemoryStore):
    _durable: SqliteStoreGroup


@_scoped_operations
class SqliteOrganizationStore(InMemoryOrganizationStore):
    _durable: SqliteStoreGroup


@_scoped_operations
class SqliteOrchestrationStore(InMemoryOrchestrationStore):
    _durable: SqliteStoreGroup


@_scoped_operations
class SqliteCommunicationStore(InMemoryCommunicationStore):
    _durable: SqliteStoreGroup


@dataclass(frozen=True)
class _Collection:
    owner: Any
    attribute: str
    key_type: Any
    record_type: Any
    sequence: bool = False
    retention: str = "operational"


def _scope(record: Any) -> WorkspaceId:
    if isinstance(record, tuple):
        if not record:
            raise InvariantViolation("empty_canonical_collection")
        return _scope(record[0])
    if isinstance(record, Workspace):
        return record.id
    for name in ("workspace_id",):
        if hasattr(record, name):
            scope = getattr(record, name)
            if type(scope) is WorkspaceId:
                return scope
    for name in ("intent", "invocation", "definition", "source", "tool_version"):
        if hasattr(record, name):
            return _scope(getattr(record, name))
    raise InvariantViolation("canonical_record_requires_workspace")


def _version(record: Any) -> int:
    for name in ("version", "revision", "entity_version", "to_version"):
        value = getattr(record, name, None)
        if isinstance(value, Version):
            return value.value
    return 1


class SqliteToolRegistry:
    """Durable configuration; executable implementations are explicitly rebound."""
    def __init__(self, group: SqliteStoreGroup) -> None:
        self.group = group
        self._executors: dict[t.ToolGrant, ToolExecutor] = {}

    def publish(self, version: t.ToolVersion, executor: ToolExecutor) -> None:
        with self.group.transaction():
            self.group.domain.get_workspace(version.definition.workspace_id)
            records = self.group._tools
            if version.grant in records:
                raise InvariantViolation("published_tool_version_immutable")
            lineage = [r.tool_version for r in records.values() if r.tool_version.definition.id == version.definition.id]
            if version.version.value != len(lineage) + 1 or (lineage and lineage[0].definition != version.definition):
                raise InvariantViolation("tool_version_lineage")
            records[version.grant] = t.ToolRegistration(version)
        self._executors[version.grant] = executor

    def bind(self, grant: t.ToolGrant, executor: ToolExecutor) -> None:
        with self.group.transaction():
            if grant not in self.group._tools:
                raise t.ToolFailure(t.ToolError.NOT_FOUND)
        self._executors[grant] = executor

    def known(self, workspace_id: WorkspaceId, tool_id: t.ToolId) -> bool:
        with self.group.transaction():
            return any(r.tool_version.definition.workspace_id == workspace_id and grant.tool_id == tool_id for grant, r in self.group._tools.items())

    def set_enabled(self, workspace_id: WorkspaceId, tool_id: t.ToolId, enabled: bool) -> None:
        with self.group.transaction():
            if not self.known(workspace_id, tool_id):
                raise t.ToolFailure(t.ToolError.UNAUTHORIZED)
            for grant, record in tuple(self.group._tools.items()):
                if grant.tool_id == tool_id:
                    self.group._tools[grant] = replace(record, enabled=enabled, revision=record.revision + 1)

    def resolve(self, workspace_id: WorkspaceId, grant: t.ToolGrant) -> ResolvedTool:
        with self.group.transaction():
            record = self.group._tools.get(grant)
            if record is None:
                raise t.ToolFailure(t.ToolError.NOT_FOUND)
            if record.tool_version.definition.workspace_id != workspace_id or not record.enabled:
                raise t.ToolFailure(t.ToolError.UNAUTHORIZED)
            executor = self._executors.get(grant)
            if executor is None:
                raise t.ToolFailure(t.ToolError.UPSTREAM_UNAVAILABLE)
            return ResolvedTool(record.tool_version, executor, record.revision)


class SqliteStoreGroup:
    """Own and close ONE connection for the complete canonical service graph.

    Construct with an explicitly migrated path. Fault callback is trusted test-only
    injection and is never loaded from persisted data. Services use the typed store
    properties; they do not access this adapter's SQL connection.
    """

    def __init__(self, path: Path, fault: Callable[[str], None] | None = None) -> None:
        self.connection = open_database(path)
        self.fault = fault or (lambda phase: None)
        self._lock = RLock()
        self._depth = 0
        self._tools: dict[t.ToolGrant, t.ToolRegistration] = {}
        self.registry = SqliteToolRegistry(self)
        self.domain = SqliteDomainStore()
        self.runtime = SqliteRuntimeStore(self.domain)
        self.knowledge = SqliteKnowledgeStore(self.runtime)
        self.memory = SqliteMemoryStore(self.runtime)
        self.organization = SqliteOrganizationStore(self.runtime)
        self.orchestration = SqliteOrchestrationStore(self.runtime)
        self.communication = SqliteCommunicationStore(self.orchestration)
        for store in (
            self.domain,
            self.runtime,
            self.knowledge,
            self.memory,
            self.organization,
            self.orchestration,
            self.communication,
        ):
            store._durable = self
        self._domain = {
            "workspace": _Collection(self.domain, "_workspaces", WorkspaceId, Workspace),
            "goal": _Collection(self.domain, "_goals", GoalId, Goal),
            "task": _Collection(self.domain, "_tasks", TaskId, Task),
            "execution": _Collection(self.domain, "_executions", ExecutionId, Execution),
            "task_attempt": _Collection(self.domain, "_attempts", TaskAttemptId, TaskAttempt),
        }
        self._collections = {
            "tool_registry": _Collection(self, "_tools", t.ToolGrant, t.ToolRegistration),
            "definitions": _Collection(
                self.runtime,
                "_definitions",
                tuple[a.AgentDefinitionId, Version],
                a.AgentDefinitionVersion,
            ),
            "runs": _Collection(self.runtime, "_runs", a.AgentRunId, a.AgentRun),
            "actions": _Collection(
                self.runtime, "_actions", a.ActionId, Action, retention="sensitive"
            ),
            "observations": _Collection(
                self.runtime, "_observations", a.ObservationId, a.Observation, retention="sensitive"
            ),
            "invocations": _Collection(
                self.runtime,
                "_tool_invocations",
                t.ToolInvocationId,
                t.ToolInvocation,
                retention="sensitive",
            ),
            "receipts": _Collection(
                self.runtime,
                "_tool_receipts",
                t.ToolReceiptId,
                t.ToolReceipt,
                retention="sensitive",
            ),
            "policies": _Collection(
                self.runtime, "_approval_policies", WorkspaceId, g.ApprovalPolicy
            ),
            "governance": _Collection(
                self.runtime, "_governed", g.ActionIntentId, g.GovernedAction, retention="sensitive"
            ),
            "sources": _Collection(
                self.knowledge, "_sources", k.KnowledgeSourceId, k.KnowledgeSource
            ),
            "source_versions": _Collection(
                self.knowledge,
                "_versions",
                tuple[k.KnowledgeSourceId, Version],
                k.KnowledgeSourceVersion,
                retention="sensitive",
            ),
            "chunks": _Collection(
                self.knowledge,
                "_chunks",
                tuple[k.KnowledgeSourceId, Version],
                tuple[k.KnowledgeChunk, ...],
                retention="sensitive",
            ),
            "evidence": _Collection(
                self.knowledge, "_packs", k.EvidencePackId, k.EvidencePack, retention="sensitive"
            ),
            "candidates": _Collection(
                self.memory,
                "_candidates",
                m.MemoryCandidateId,
                m.MemoryCandidate,
                retention="sensitive",
            ),
            "entries": _Collection(
                self.memory, "_entries", m.MemoryEntryId, m.MemoryEntry, retention="sensitive"
            ),
            "memory_packs": _Collection(
                self.memory,
                "_packs",
                m.MemoryContextPackId,
                m.MemoryContextPack,
                retention="sensitive",
            ),
            "graphs": _Collection(self.organization, "_graphs", WorkspaceId, org.OrganizationGraph),
            "graph_versions": _Collection(
                self.organization,
                "_versions",
                tuple[WorkspaceId, Version],
                org.OrganizationGraphVersion,
            ),
            "orchestrations": _Collection(
                self.orchestration, "_runs", o.OrchestrationRunId, o.OrchestrationRun
            ),
            "plans": _Collection(
                self.orchestration, "_plans", tuple[o.OrchestrationPlanId, Version], o.PlanVersion
            ),
            "materializations": _Collection(
                self.orchestration,
                "_materializations",
                tuple[o.OrchestrationPlanId, Version],
                o.PlanMaterialization,
            ),
            "delegations": _Collection(
                self.orchestration, "_delegations", o.DelegationId, o.Delegation
            ),
            "delegation_attempts": _Collection(
                self.orchestration, "_attempts", int, o.DelegationAttempt, True
            ),
            "threads": _Collection(
                self.communication, "_threads", c.MessageThreadId, c.MessageThread
            ),
            "messages": _Collection(
                self.communication,
                "_messages",
                c.AgentMessageId,
                c.AgentMessage,
                retention="sensitive",
            ),
            "handoffs": _Collection(
                self.communication,
                "_handoffs",
                c.HandoffId,
                c.HandoffRequest,
                retention="sensitive",
            ),
        }
        for name, owner in (
            ("runtime", self.runtime),
            ("knowledge", self.knowledge),
            ("memory", self.memory),
            ("organization", self.organization),
            ("orchestration", self.orchestration),
            ("communication", self.communication),
        ):
            self._collections[name + "_events"] = _Collection(
                owner, "_events", int, Event, True, "audit"
            )
        self._collections["runtime_transitions"] = _Collection(
            self.runtime, "_transitions", int, StateTransition, True, "audit"
        )
        try:
            with self.transaction():
                pass
        except BaseException:
            self.connection.close()
            raise

    def close(self) -> None:
        if self._depth:
            raise InvariantViolation("cannot_close_active_transaction")
        self.connection.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            if self._depth:
                self._depth += 1
                try:
                    yield
                finally:
                    self._depth -= 1
                return
            self.fault("before_transaction")
            self.connection.execute("BEGIN IMMEDIATE")
            self._depth = 1
            try:
                before_domain, before_records, before_audit = self._load()
                yield
                self._flush(before_domain, before_records, before_audit)
                self.fault("before_commit")
                self.connection.commit()
            except BaseException:
                self.connection.rollback()
                # Reload on the next public operation; no stale objects authorize a write.
                raise
            finally:
                self._depth = 0
            self.fault("after_commit")

    def _load(self) -> tuple[dict[Any, Any], dict[Any, Any], set[Any]]:
        for descriptor in (*self._domain.values(), *self._collections.values()):
            setattr(descriptor.owner, descriptor.attribute, [] if descriptor.sequence else {})
        self.domain._events, self.domain._transitions = [], []
        self.domain._event_ids, self.domain._transition_ids = set(), set()
        before_domain: dict[Any, Any] = {}
        for row in self.connection.execute(
            "SELECT kind,id,workspace_id,version,status,created_at,updated_at,payload FROM domain_records ORDER BY rowid"
        ):
            kind, identity, workspace, version, status, created, updated, payload = row
            if kind not in self._domain:
                raise InvariantViolation("unknown_durable_record_type")
            descriptor = self._domain[kind]
            record = decode_record(payload, descriptor.record_type)
            if (
                str(record.id),
                str(_scope(record)),
                record.version.value,
                record.status.value,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
            ) != (identity, workspace, version, status, created, updated):
                raise InvariantViolation("durable_row_payload_mismatch")
            getattr(descriptor.owner, descriptor.attribute)[record.id] = record
            before_domain[(kind, identity)] = (version, payload)
        before_audit: set[Any] = set()
        for (
            kind,
            identity,
            workspace,
            subject_kind,
            subject,
            occurred,
            payload,
        ) in self.connection.execute(
            "SELECT kind,id,workspace_id,subject_kind,subject_id,occurred_at,payload FROM domain_audit ORDER BY rowid"
        ):
            audit = (
                decode_record(payload, Event)
                if kind == "event"
                else decode_record(payload, StateTransition)
            )
            if (
                str(audit.id),
                str(audit.workspace_id),
                audit.subject_type.value,
                audit.subject_id,
                audit.occurred_at.isoformat(),
            ) != (identity, workspace, subject_kind, subject, occurred):
                raise InvariantViolation("durable_audit_payload_mismatch")
            if isinstance(audit, Event):
                self.domain._events.append(audit)
                self.domain._event_ids.add(audit.id)
            else:
                self.domain._transitions.append(audit)
                self.domain._transition_ids.add(audit.id)
            before_audit.add((kind, identity))
        before_records: dict[Any, Any] = {}
        for (
            name,
            key_json,
            schema,
            workspace,
            revision,
            version,
            retention,
            payload,
        ) in self.connection.execute(
            "SELECT collection,record_key,schema_version,workspace_id,revision,entity_version,retention,payload FROM canonical_records ORDER BY rowid"
        ):
            if name not in self._collections or schema != 1:
                raise InvariantViolation("unknown_durable_record_type")
            descriptor = self._collections[name]
            key = decode_value(key_json, descriptor.key_type)
            record = decode_value(payload, descriptor.record_type)
            if (str(_scope(record)), _version(record), retention) != (
                workspace,
                version,
                descriptor.retention,
            ):
                raise InvariantViolation("durable_row_payload_mismatch")
            container = getattr(descriptor.owner, descriptor.attribute)
            if descriptor.sequence:
                if key != len(container):
                    raise InvariantViolation("durable_sequence_gap")
                container.append(record)
            else:
                container[key] = record
            before_records[(name, key_json)] = (revision, payload)
        if self.connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise InvariantViolation("durable_foreign_key_corruption")
        return before_domain, before_records, before_audit

    def _flush(
        self, before_domain: dict[Any, Any], before: dict[Any, Any], audit_ids: set[Any]
    ) -> None:
        for kind, descriptor in self._domain.items():
            for record in getattr(descriptor.owner, descriptor.attribute).values():
                payload = encode_record(record)
                identity = (kind, str(record.id))
                old = before_domain.get(identity)
                if old and old[1] == payload:
                    continue
                self.fault("state_write")
                if old:
                    cursor = self.connection.execute(
                        "UPDATE domain_records SET version=?,status=?,updated_at=?,payload=? WHERE kind=? AND id=? AND version=?",
                        (
                            record.version.value,
                            record.status.value,
                            record.updated_at.isoformat(),
                            payload,
                            *identity,
                            old[0],
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise InvariantViolation("durable_version_conflict")
                else:
                    self.connection.execute(
                        "INSERT INTO domain_records(kind,id,workspace_id,version,status,created_at,updated_at,payload,goal_id,task_id,execution_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            *identity,
                            str(_scope(record)),
                            record.version.value,
                            record.status.value,
                            record.created_at.isoformat(),
                            record.updated_at.isoformat(),
                            payload,
                            str(record.goal_id) if hasattr(record, "goal_id") else None,
                            str(record.task_id) if isinstance(record, TaskAttempt) else None,
                            str(record.execution_id) if isinstance(record, TaskAttempt) else None,
                        ),
                    )
        for kind, records in (
            ("event", self.domain._events),
            ("transition", self.domain._transitions),
        ):
            for record in records:
                if (kind, str(record.id)) not in audit_ids:
                    self.fault("audit_write")
                    self.connection.execute(
                        "INSERT INTO domain_audit VALUES (?,?,?,?,?,?,?)",
                        (
                            kind,
                            str(record.id),
                            str(record.workspace_id),
                            record.subject_type.value,
                            record.subject_id,
                            record.occurred_at.isoformat(),
                            encode_record(record),
                        ),
                    )
        rows: dict[tuple[str, str], Any] = {}
        for name, descriptor in self._collections.items():
            container = getattr(descriptor.owner, descriptor.attribute)
            entries = enumerate(container) if descriptor.sequence else container.items()
            for key, record in entries:
                key_json = encode_value(key, descriptor.key_type)
                payload = encode_value(record, descriptor.record_type)
                identity = (name, key_json)
                rows[identity] = record
                old = before.get(identity)
                if old and old[1] == payload:
                    continue
                self.fault("audit_write" if descriptor.retention == "audit" else "state_write")
                if old:
                    if descriptor.sequence:
                        raise InvariantViolation("durable_history_immutable")
                    cursor = self.connection.execute(
                        "UPDATE canonical_records SET payload=?,entity_version=?,revision=revision+1 WHERE collection=? AND record_key=? AND revision=?",
                        (payload, _version(record), *identity, old[0]),
                    )
                    if cursor.rowcount != 1:
                        raise InvariantViolation("durable_version_conflict")
                else:
                    self.connection.execute(
                        "INSERT INTO canonical_records(collection,record_key,schema_version,workspace_id,revision,entity_version,retention,payload) VALUES (?,?,1,?,1,?,?,?)",
                        (
                            *identity,
                            str(_scope(record)),
                            _version(record),
                            descriptor.retention,
                            payload,
                        ),
                    )
        if set(before) - set(rows):
            raise InvariantViolation("canonical_deletion_not_supported")
        # Typed foreign-key lineage between canonical records. Snapshots embed exact
        # versions; links constrain their stable IDs to the same workspace.
        ids: dict[OpaqueId, tuple[str, str]] = {}
        for identity, record in rows.items():
            candidate = getattr(record, "id", None)
            if isinstance(candidate, OpaqueId):
                ids.setdefault(candidate, identity)
            if isinstance(record, g.GovernedAction):
                ids[record.intent.id] = identity

        def references(value: Any) -> Iterator[OpaqueId]:
            if isinstance(value, OpaqueId):
                yield value
            elif is_dataclass(value):
                for field in fields(value):
                    yield from references(getattr(value, field.name))
            elif isinstance(value, tuple):
                for item in value:
                    yield from references(item)

        for identity, record in rows.items():
            for reference in set(references(record)):
                target = ids.get(reference)
                if target is not None and target != identity:
                    self.connection.execute(
                        "INSERT OR IGNORE INTO canonical_links VALUES (?,?,?,?,?)",
                        (str(_scope(record)), *identity, *target),
                    )
