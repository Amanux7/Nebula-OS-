"""Workspace-scoped, read-only audit projections over canonical stores.

Views intentionally omit source content, model payloads, fixture messages, and human
free-text reasons. Protected entity reads remain separate from generic timelines.
"""

from dataclasses import dataclass
from datetime import datetime
from time import perf_counter_ns
from typing import Protocol

from agent_company_os.domain.agent import AgentRunId
from agent_company_os.domain.errors import InvariantViolation, WorkspaceMismatch
from agent_company_os.domain.events import Event
from agent_company_os.domain.governance import ActionIntentId, GovernedAction
from agent_company_os.domain.ids import EventId, ExecutionId, GoalId, TaskId, WorkspaceId
from agent_company_os.ports.orchestration import OrchestrationStore
from agent_company_os.ports.runtime_store import RuntimeStore


class AuditEventSource(Protocol):
    def events(self, workspace_id: WorkspaceId) -> tuple[Event, ...]: ...


_CORRELATION = frozenset(
    {
        "goal_id",
        "task_id",
        "task_attempt_id",
        "execution_id",
        "agent_run_id",
        "run_id",
        "action_id",
        "action_intent_id",
        "intent_id",
        "tool_invocation_id",
        "tool_receipt_id",
        "orchestration_run_id",
        "delegation_id",
        "plan_id",
        "observation_id",
    }
)
_SAFE = _CORRELATION | frozenset(
    {
        "fingerprint",
        "risk",
        "policy_version",
        "tool_version",
        "status",
        "error_code",
        "reason_code",
        "duration_ms",
        "input_bytes",
        "output_bytes",
        "retry_count",
    }
)


@dataclass(frozen=True)
class TimelineEntry:
    event_id: EventId
    timestamp: datetime
    workspace_id: WorkspaceId
    event_kind: str
    subject_type: str
    subject_id: str
    metadata: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ApprovalView:
    intent_id: str
    fingerprint: str
    actor_id: str
    policy_version: int
    decisions: tuple[str, ...]
    expires_at: datetime
    consumed: bool
    cancelled: bool


@dataclass(frozen=True)
class InvocationView:
    invocation_id: str
    run_id: str
    action_id: str
    tool_id: str
    tool_version: int
    status: str
    outcome: str
    receipt_id: str | None


@dataclass(frozen=True)
class TraceLink:
    goal_id: str
    task_id: str
    task_attempt_id: str
    agent_run_id: str
    action_intent_id: str | None
    approval_fingerprint: str | None
    invocation_id: str | None
    receipt_id: str | None


class AuditQueryService:
    def __init__(
        self,
        store: RuntimeStore,
        sources: tuple[AuditEventSource, ...] = (),
        orchestration: OrchestrationStore | None = None,
    ) -> None:
        self.store, self.sources = store, sources
        if orchestration is not None and orchestration.runtime is not store:
            raise InvariantViolation("audit_orchestration_binding")
        self.orchestration = orchestration
        self.query_count = 0  # Derived process-local telemetry, not authorization state.
        self.query_latency_ns = 0

    @staticmethod
    def _scope(expected: WorkspaceId, actual: WorkspaceId) -> None:
        if type(expected) is not WorkspaceId or expected != actual:
            raise WorkspaceMismatch("audit_subject", str(expected), str(actual))

    def _timeline(self, workspace: WorkspaceId, identities: set[str]) -> tuple[TimelineEntry, ...]:
        started = perf_counter_ns()
        self.store.domain.get_workspace(workspace)
        events = [*self.store.domain.events(workspace), *self.store.events(workspace)]
        for source in self.sources:
            events.extend(source.events(workspace))
        if self.orchestration is not None:
            events.extend(self.orchestration.events(workspace))
        selected: dict[EventId, Event] = {}
        for event in events:
            self._scope(workspace, event.workspace_id)
            if event.subject_id in identities or any(
                key in _CORRELATION and value in identities for key, value in event.metadata
            ):
                if event.id in selected and selected[event.id] != event:
                    raise InvariantViolation("audit_event_identity_collision")
                selected[event.id] = event
        self.query_count += 1
        result = tuple(
            TimelineEntry(
                e.id,
                e.occurred_at,
                e.workspace_id,
                e.event_type.value,
                e.subject_type.value,
                e.subject_id,
                tuple(
                    (key, value) for key, value in e.metadata if key in _SAFE and len(value) <= 256
                ),
            )
            for e in sorted(selected.values(), key=lambda event: (event.occurred_at, str(event.id)))
        )
        self.query_latency_ns += perf_counter_ns() - started
        return result

    def timeline_for_goal(
        self, workspace: WorkspaceId, goal_id: GoalId
    ) -> tuple[TimelineEntry, ...]:
        with self.store.atomic():
            self._scope(workspace, self.store.domain.get_goal(goal_id).workspace_id)
            identities = {str(goal_id)} | {
                str(t.id) for t in self.store.domain.tasks_for_goal(goal_id)
            }
            for task in self.store.domain.tasks_for_goal(goal_id):
                for attempt in self.store.domain.attempts_for_task(task.id):
                    identities.update((str(attempt.id), str(attempt.execution_id)))
            for run in self.store.runs(workspace):
                if run.goal_id == goal_id:
                    identities.update(
                        (str(run.id), str(run.execution_id), str(run.task_attempt_id))
                    )
            if self.orchestration is not None:
                for parent in self.orchestration.runs(workspace):
                    if parent.goal_id == goal_id:
                        identities.add(str(parent.id))
                        identities.update(
                            str(plan.id) for plan in self.orchestration.plans(workspace, parent.id)
                        )
                        identities.update(
                            str(d.id) for d in self.orchestration.delegations(workspace, parent.id)
                        )
            return self._timeline(workspace, identities)

    def timeline_for_task(
        self, workspace: WorkspaceId, task_id: TaskId
    ) -> tuple[TimelineEntry, ...]:
        with self.store.atomic():
            self._scope(workspace, self.store.domain.get_task(task_id).workspace_id)
            identities = {str(task_id)} | {
                str(run.id) for run in self.store.runs(workspace) if run.task_id == task_id
            }
            identities.update(
                str(attempt.id) for attempt in self.store.domain.attempts_for_task(task_id)
            )
            return self._timeline(workspace, identities)

    def timeline_for_agent_run(
        self, workspace: WorkspaceId, run_id: AgentRunId
    ) -> tuple[TimelineEntry, ...]:
        with self.store.atomic():
            self.store.get_run(workspace, run_id)
            return self._timeline(workspace, {str(run_id)})

    def timeline_for_action_intent(
        self, workspace: WorkspaceId, intent_id: ActionIntentId
    ) -> tuple[TimelineEntry, ...]:
        with self.store.atomic():
            record = self.store.governed_action(workspace, intent_id)
            ids = {str(intent_id), str(record.intent.action_id)}
            if record.invocation_id is not None:
                ids.add(str(record.invocation_id))
            return self._timeline(workspace, ids)

    def approvals_for_task(
        self, workspace: WorkspaceId, task_id: TaskId
    ) -> tuple[ApprovalView, ...]:
        with self.store.atomic():
            self._scope(workspace, self.store.domain.get_task(task_id).workspace_id)
            return tuple(
                ApprovalView(
                    str(g.intent.id),
                    g.intent.fingerprint,
                    str(g.intent.run_id),
                    g.intent.policy.version.value,
                    tuple(d.kind.value for d in g.decisions),
                    g.intent.expires_at,
                    g.consumed,
                    g.cancelled,
                )
                for g in sorted(
                    self.store.governed_actions(workspace), key=lambda g: str(g.intent.id)
                )
                if g.intent.task_id == task_id
            )

    def tool_invocations_for_execution(
        self, workspace: WorkspaceId, execution_id: ExecutionId
    ) -> tuple[InvocationView, ...]:
        with self.store.atomic():
            self._scope(workspace, self.store.domain.get_execution(execution_id).workspace_id)
            result: list[InvocationView] = []
            for run in self.store.runs(workspace):
                if run.execution_id != execution_id:
                    continue
                receipts = {r.invocation.id: r for r in self.store.tool_receipts(workspace, run.id)}
                for invocation in self.store.tool_invocations(workspace, run.id):
                    receipt = receipts.get(invocation.id)
                    result.append(
                        InvocationView(
                            str(invocation.id),
                            str(run.id),
                            str(invocation.action_id),
                            str(invocation.tool_version.definition.id),
                            invocation.tool_version.version.value,
                            invocation.status.value,
                            "outcome_unknown"
                            if receipt is None or receipt.remote_outcome == "unknown"
                            else "observed_success"
                            if receipt.output
                            else "observed_failure",
                            str(receipt.id) if receipt else None,
                        )
                    )
            return tuple(sorted(result, key=lambda item: item.invocation_id))

    def trace_goal(self, workspace: WorkspaceId, goal_id: GoalId) -> tuple[TraceLink, ...]:
        with self.store.atomic():
            self._scope(workspace, self.store.domain.get_goal(goal_id).workspace_id)
            result: list[TraceLink] = []
            governed = self.store.governed_actions(workspace)
            for run in self.store.runs(workspace):
                if run.goal_id != goal_id:
                    continue
                intents: list[GovernedAction | None] = [
                    record for record in governed if record.intent.run_id == run.id
                ]
                for record in intents or [None]:
                    receipt = next(
                        (
                            r
                            for r in self.store.tool_receipts(workspace, run.id)
                            if record is not None and r.invocation.id == record.invocation_id
                        ),
                        None,
                    )
                    result.append(
                        TraceLink(
                            str(goal_id),
                            str(run.task_id),
                            str(run.task_attempt_id),
                            str(run.id),
                            str(record.intent.id) if record else None,
                            record.intent.fingerprint if record else None,
                            str(record.invocation_id) if record and record.invocation_id else None,
                            str(receipt.id) if receipt else None,
                        )
                    )
            return tuple(
                sorted(result, key=lambda item: (item.agent_run_id, item.action_intent_id or ""))
            )
