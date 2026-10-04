"""Initial authenticated read DTOs; no SQL, model calls, or canonical mutations.

Offset pages are bounded and stable under a static dataset, not snapshot cursors.
The host also enforces a pre-decode record/byte budget on the SQLite adapter.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from agent_company_os.application.audit import AuditQueryService, TimelineEntry
from agent_company_os.application.operator import OperatorService
from agent_company_os.application.recovery import RecoveryService
from agent_company_os.domain.agent import AgentRunId
from agent_company_os.domain.errors import EntityNotFound, InvariantViolation
from agent_company_os.domain.goal import GoalStatus
from agent_company_os.domain.ids import GoalId, TaskId, WorkspaceId
from agent_company_os.domain.operator import OperatorResource
from agent_company_os.domain.recovery import RecoveryCase
from agent_company_os.ports.inspection import (
    InspectionCatalog,
    InspectionLineage,
    InspectionLink,
    InspectionRecord,
    LineageSection,
)
from agent_company_os.ports.runtime_store import RuntimeStore


@dataclass(frozen=True)
class ReadPage[T]:
    items: tuple[T, ...]
    next_cursor: str | None


def _page[T](items: tuple[T, ...], limit: int, cursor: str | None) -> ReadPage[T]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise InvariantViolation("operator_page_limit")
    if cursor is not None and (
        type(cursor) is not str
        or not cursor.isascii()
        or not cursor.isdecimal()
        or len(cursor) > 7
        or str(int(cursor)) != cursor
        or int(cursor) > 1_000_000
    ):
        raise InvariantViolation("operator_page_cursor")
    offset = int(cursor) if cursor else 0
    selected = items[offset : offset + limit]
    following = offset + len(selected)
    return ReadPage(selected, str(following) if following < len(items) else None)


@dataclass(frozen=True)
class GoalSummary:
    id: str
    workspace_id: str
    objective: str
    status: str
    version: int
    updated_at: datetime


@dataclass(frozen=True)
class TaskSummary:
    id: str
    goal_id: str
    title: str
    status: str
    version: int


@dataclass(frozen=True)
class AgentRunSummary:
    id: str
    goal_id: str
    task_id: str
    execution_id: str
    task_attempt_id: str
    definition_id: str
    definition_version: int
    status: str
    version: int
    iteration: int
    deadline: datetime
    invocation_pending: bool
    evidence_pack_id: str | None
    memory_pack_id: str | None
    result_available: bool


@dataclass(frozen=True)
class RecoveryIncidentSummary:
    subject_type: str
    subject_id: str
    reason: str
    outcome: str
    explanation: str
    links: tuple[InspectionLink, ...]


RECOVERY_TEXT = {
    "resume_local_state": "Inspect persisted state for local repair. No dispatch is implied.",
    "safe_to_retry": "Candidate only. Non-execution evidence and current authority are required.",
    "awaiting_human_approval": "Work is waiting on an exact-action human decision.",
    "connector_reconciliation_required": (
        "Dispatch was claimed without a receipt. Look up remote status; do not retry the write."
    ),
    "manual_review_required": (
        "Evidence or authority is missing. Restored intents stay blocked after release."
    ),
    "terminal_unknown": "The recorded external outcome is unknown. It is not a retryable failure.",
    "expired": "The persisted deadline or approval expiry has passed.",
    "cancelled": "Work was cancelled. Cancellation does not undo a remote effect.",
}

LINEAGE_KINDS = (
    "goals",
    "tasks",
    "attempts",
    "executions",
    "runs",
    "orchestrations",
    "plans",
    "materializations",
    "delegations",
    "delegation_attempts",
    "results",
    "messages",
    "threads",
    "handoffs",
    "intents",
    "approvals",
    "approval_requests",
    "approval_decisions",
    "invocations",
    "receipts",
)


class OperatorQueryService:
    def __init__(
        self,
        operators: OperatorService,
        runtime: RuntimeStore,
        audit: AuditQueryService,
        recovery: RecoveryService,
        catalog: InspectionCatalog | None = None,
    ) -> None:
        if (
            operators.domain is not runtime.domain
            or recovery.store is not runtime
            or audit.store is not runtime
        ):
            raise InvariantViolation("operator_query_store_binding")
        self.operators, self.runtime, self.audit_query, self.recovery = (
            operators,
            runtime,
            audit,
            recovery,
        )
        self.catalog = catalog

    def lineage(
        self, token: str, workspace: WorkspaceId, kind: str, entity_id: str
    ) -> InspectionLineage:
        with self._scope(token, workspace, OperatorResource.OPERATIONAL):
            if self.catalog is None or kind not in LINEAGE_KINDS:
                raise InvariantViolation("unsupported_lineage_kind")
            rows = {
                category: self.catalog.records(workspace, category) for category in LINEAGE_KINDS
            }
            root = next((r for r in rows[kind] if r.id == entity_id), None)
            if root is None:
                raise EntityNotFound(kind, entity_id)
            selected = {(kind, entity_id)}
            # Inbound structural references only: do not fan out through common Workspace
            # or AgentDefinition ancestors into unrelated work.
            for _ in range(12):
                before = len(selected)
                for category, records in rows.items():
                    for record in records:
                        if any((link.kind, link.id) in selected for link in record.links):
                            selected.add((category, record.id))
                if len(selected) == before:
                    break
            sections = []
            for category, records in rows.items():
                matches = tuple(
                    r
                    for r in records
                    if (category, r.id) in selected and (category, r.id) != (kind, entity_id)
                )
                if matches:
                    sections.append(LineageSection(category, matches[:100], len(matches) > 100))
            return InspectionLineage(root, tuple(sections))

    def inspect(
        self,
        token: str,
        workspace: WorkspaceId,
        kind: str,
        *,
        limit: int = 25,
        cursor: str | None = None,
        entity_id: str | None = None,
        goal_id: str | None = None,
    ) -> ReadPage[InspectionRecord]:
        with self._scope(token, workspace, OperatorResource.OPERATIONAL):
            if self.catalog is None:
                raise InvariantViolation("inspection_catalog_unavailable")
            for value in (entity_id, goal_id):
                if value is not None and (not value or len(value) > 256):
                    raise InvariantViolation("invalid_inspection_filter")
            records = self.catalog.records(workspace, kind)
            if entity_id is not None:
                records = tuple(record for record in records if record.id == entity_id)
                if not records:
                    raise EntityNotFound(kind, entity_id)
            if goal_id is not None:
                records = tuple(
                    record for record in records if ("goal_id", goal_id) in record.fields
                )
            return _page(records, limit, cursor)

    @contextmanager
    def _scope(
        self, token: str, workspace: WorkspaceId, resource: OperatorResource
    ) -> Iterator[None]:
        with self.operators.store.atomic():
            self.operators.authorize(token, workspace, resource)
            with self.runtime.atomic():
                yield

    def goals(
        self,
        token: str,
        workspace: WorkspaceId,
        *,
        limit: int = 25,
        cursor: str | None = None,
        status: GoalStatus | None = None,
    ) -> ReadPage[GoalSummary]:
        with self._scope(token, workspace, OperatorResource.OPERATIONAL):
            if status is not None and type(status) is not GoalStatus:
                raise InvariantViolation("operator_goal_filter")
            goals = sorted(self.runtime.domain.goals(workspace), key=lambda g: str(g.id))
            return _page(
                tuple(
                    GoalSummary(
                        str(g.id),
                        str(workspace),
                        g.objective[:500],
                        g.status.value,
                        g.version.value,
                        g.updated_at,
                    )
                    for g in goals
                    if status is None or g.status is status
                ),
                limit,
                cursor,
            )

    def task(self, token: str, workspace: WorkspaceId, task_id: TaskId) -> TaskSummary:
        with self._scope(token, workspace, OperatorResource.OPERATIONAL):
            task = self.runtime.domain.get_task(task_id)
            if task.workspace_id != workspace:
                raise EntityNotFound("Task", str(task_id))
            return TaskSummary(
                str(task.id),
                str(task.goal_id),
                task.title[:500],
                task.status.value,
                task.version.value,
            )

    def run(self, token: str, workspace: WorkspaceId, run_id: AgentRunId) -> AgentRunSummary:
        with self._scope(token, workspace, OperatorResource.OPERATIONAL):
            run = self.runtime.get_run(workspace, run_id)
            state = run.working_state
            return AgentRunSummary(
                str(run.id),
                str(run.goal_id),
                str(run.task_id),
                str(run.execution_id),
                str(run.task_attempt_id),
                str(run.definition_version.definition.id),
                run.definition_version.version.value,
                run.status.value,
                run.version.value,
                state.iteration,
                run.deadline,
                state.invocation_pending,
                str(state.active_evidence_pack_id) if state.active_evidence_pack_id else None,
                str(state.active_memory_pack_id) if state.active_memory_pack_id else None,
                run.result is not None,
            )

    def goal_timeline(
        self,
        token: str,
        workspace: WorkspaceId,
        goal_id: GoalId,
        *,
        limit: int = 25,
        cursor: str | None = None,
    ) -> ReadPage[TimelineEntry]:
        with self._scope(token, workspace, OperatorResource.AUDIT):
            return _page(self.audit_query.timeline_for_goal(workspace, goal_id), limit, cursor)

    def recovery_cases(
        self,
        token: str,
        workspace: WorkspaceId,
        *,
        limit: int = 25,
        cursor: str | None = None,
    ) -> ReadPage[RecoveryCase]:
        with self._scope(token, workspace, OperatorResource.RECOVERY):
            return _page(self.recovery.classify(workspace), limit, cursor)

    def recovery_incidents(
        self,
        token: str,
        workspace: WorkspaceId,
        *,
        limit: int = 25,
        cursor: str | None = None,
    ) -> ReadPage[RecoveryIncidentSummary]:
        page = self.recovery_cases(token, workspace, limit=limit, cursor=cursor)
        categories = {
            "agent_run": "runs",
            "task_attempt": "attempts",
            "execution": "executions",
            "orchestration_run": "orchestrations",
            "action_intent": "intents",
            "tool_invocation": "invocations",
        }
        return ReadPage(
            tuple(
                RecoveryIncidentSummary(
                    c.subject_type,
                    c.subject_id,
                    c.reason.value,
                    c.outcome,
                    RECOVERY_TEXT[c.reason.value],
                    (InspectionLink("Related record", categories[c.subject_type], c.subject_id),),
                )
                for c in page.items
            ),
            page.next_cursor,
        )
