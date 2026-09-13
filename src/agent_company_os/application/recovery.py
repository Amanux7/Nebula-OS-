"""Deterministic recovery classification and connector-evidence reconciliation.

No method in this module calls a model or dispatches a consequential operation.
Safe-to-retry is an eligibility assessment, never reusable authorization.
"""

from agent_company_os.application.tool_runtime import ToolRuntimeService
from agent_company_os.application.tool_validation import input_json, validate_output
from agent_company_os.domain.agent import AgentRun, AgentRunId, AgentRunStatus
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.events import Event, EventType
from agent_company_os.domain.governance import DecisionKind
from agent_company_os.domain.ids import WorkspaceId
from agent_company_os.domain.recovery import (
    RecoveryCase,
    RecoveryReason,
    RemoteStatus,
    execution_key,
)
from agent_company_os.domain.tools import (
    ToolError,
    ToolInvocation,
    ToolInvocationId,
    ToolInvocationStatus,
    ToolReceipt,
    ToolRisk,
)
from agent_company_os.domain.transitions import SubjectType
from agent_company_os.ports.clock import Clock
from agent_company_os.ports.ids import IdGenerator
from agent_company_os.ports.recovery import RecoveryConnector
from agent_company_os.ports.runtime_store import RuntimeStore


class RecoveryService:
    def __init__(
        self, store: RuntimeStore, tools: ToolRuntimeService, clock: Clock, ids: IdGenerator
    ) -> None:
        if tools.store is not store:
            raise InvariantViolation("recovery_store_binding")
        self.store, self.tools, self.clock, self.ids = store, tools, clock, ids

    def classify(self, workspace: WorkspaceId) -> tuple[RecoveryCase, ...]:
        cases: list[RecoveryCase] = []
        with self.store.atomic():
            for run in self.store.runs(workspace):
                if run.status not in (AgentRunStatus.RUNNING, AgentRunStatus.WAITING):
                    continue
                reason = RecoveryReason.RESUME_LOCAL
                if self.clock.now() >= run.deadline:
                    reason = RecoveryReason.EXPIRED
                elif run.status is AgentRunStatus.WAITING:
                    reason = (
                        RecoveryReason.AWAITING_APPROVAL
                        if run.working_state.invocation_pending
                        else RecoveryReason.RESUME_LOCAL
                    )
                elif run.working_state.invocation_pending:
                    reason = (
                        RecoveryReason.MANUAL_REVIEW
                    )  # Lost model result is not guessed/replayed.
                cases.append(
                    RecoveryCase(workspace, "agent_run", str(run.id), reason, "not_executed")
                )
                for kind, identity in (
                    ("task_attempt", run.task_attempt_id),
                    ("execution", run.execution_id),
                ):
                    cases.append(
                        RecoveryCase(workspace, kind, str(identity), reason, "not_executed")
                    )
            for record in self.store.governed_actions(workspace):
                if record.invocation_id is None:
                    reason = RecoveryReason.AWAITING_APPROVAL
                    if record.cancelled:
                        reason = RecoveryReason.CANCELLED
                    elif self.clock.now() >= record.intent.expires_at:
                        reason = RecoveryReason.EXPIRED
                    elif (
                        record.decisions and record.decisions[-1].kind is not DecisionKind.APPROVED
                    ):
                        reason = RecoveryReason.MANUAL_REVIEW
                    cases.append(
                        RecoveryCase(
                            workspace,
                            "action_intent",
                            str(record.intent.id),
                            reason,
                            "not_executed",
                        )
                    )
            # Include claims of terminal runs too: cancellation does not establish remote outcome.
            for run in self.store.runs(workspace):
                receipts = {r.invocation.id: r for r in self.store.tool_receipts(workspace, run.id)}
                for invocation in self.store.tool_invocations(workspace, run.id):
                    receipt = receipts.get(invocation.id)
                    if receipt is None:
                        reason = (
                            RecoveryReason.SAFE_TO_RETRY
                            if invocation.tool_version.definition.risk is ToolRisk.READ_ONLY
                            else RecoveryReason.CONNECTOR_REQUIRED
                        )
                        cases.append(
                            RecoveryCase(
                                workspace,
                                "tool_invocation",
                                str(invocation.id),
                                reason,
                                "outcome_unknown",
                            )
                        )
                    elif receipt.remote_outcome == "unknown":
                        cases.append(
                            RecoveryCase(
                                workspace,
                                "tool_invocation",
                                str(invocation.id),
                                RecoveryReason.TERMINAL_UNKNOWN,
                                "outcome_unknown",
                            )
                        )
                    elif run.working_state.invocation_pending:
                        cases.append(
                            RecoveryCase(
                                workspace,
                                "tool_invocation",
                                str(invocation.id),
                                RecoveryReason.RESUME_LOCAL,
                                "observed_success" if receipt.output else "observed_failure",
                            )
                        )
        return tuple(sorted(set(cases), key=lambda case: (case.subject_type, case.subject_id)))

    def _event(
        self, run: AgentRun, invocation: ToolInvocation, kind: EventType, reason: str
    ) -> None:
        self.store.append_event(
            Event(
                self.ids.event_id(),
                run.workspace_id,
                kind,
                SubjectType.AGENT_RUN,
                str(run.id),
                run.version,
                self.clock.now(),
                (
                    ("tool_invocation_id", str(invocation.id)),
                    ("action_id", str(invocation.action_id)),
                    ("execution_id", str(run.execution_id)),
                    ("reason_code", reason),
                ),
            )
        )

    async def reconcile(
        self,
        workspace: WorkspaceId,
        run_id: AgentRunId,
        invocation_id: ToolInvocationId,
        connector: RecoveryConnector,
    ) -> RecoveryCase:
        with self.store.atomic():
            run = self.store.get_run(workspace, run_id)
            invocation = next(
                (
                    i
                    for i in self.store.tool_invocations(workspace, run_id)
                    if i.id == invocation_id
                ),
                None,
            )
            if invocation is None:
                raise InvariantViolation("recovery_invocation_missing")
            existing = next(
                (
                    r
                    for r in self.store.tool_receipts(workspace, run_id)
                    if r.invocation.id == invocation_id
                ),
                None,
            )
            if existing is not None:
                self.tools.reconcile_receipt(existing)
                return RecoveryCase(
                    workspace,
                    "tool_invocation",
                    str(invocation_id),
                    RecoveryReason.TERMINAL_UNKNOWN
                    if existing.remote_outcome == "unknown"
                    else RecoveryReason.RESUME_LOCAL,
                    "outcome_unknown"
                    if existing.remote_outcome == "unknown"
                    else "observed_success"
                    if existing.output
                    else "observed_failure",
                )
            self._event(run, invocation, EventType.RECOVERY_DETECTED, "claimed_without_receipt")
        if not connector.capabilities.supports_status_lookup:
            return RecoveryCase(
                workspace,
                "tool_invocation",
                str(invocation_id),
                RecoveryReason.MANUAL_REVIEW,
                "outcome_unknown",
            )
        # Lookup is external I/O: no canonical transaction remains open here.
        lookup = await connector.lookup_status(execution_key(invocation))
        with self.store.atomic():
            run = self.store.get_run(workspace, run_id)
            current = next(
                i for i in self.store.tool_invocations(workspace, run_id) if i.id == invocation_id
            )
            existing = next(
                (
                    r
                    for r in self.store.tool_receipts(workspace, run_id)
                    if r.invocation.id == invocation_id
                ),
                None,
            )
            if existing is not None:
                self.tools.reconcile_receipt(existing)
                return RecoveryCase(
                    workspace,
                    "tool_invocation",
                    str(invocation_id),
                    RecoveryReason.RESUME_LOCAL,
                    "observed_success" if existing.output else "outcome_unknown",
                )
            if current != invocation or invocation.status is not ToolInvocationStatus.RUNNING:
                raise InvariantViolation("recovery_invocation_changed")
            self._event(run, invocation, EventType.RECOVERY_LOOKUP, lookup.status.value)
            if lookup.status in (RemoteStatus.UNKNOWN, RemoteStatus.NEVER_RECEIVED):
                return RecoveryCase(
                    workspace,
                    "tool_invocation",
                    str(invocation_id),
                    RecoveryReason.SAFE_TO_RETRY
                    if lookup.status is RemoteStatus.NEVER_RECEIVED
                    else RecoveryReason.MANUAL_REVIEW,
                    "not_executed"
                    if lookup.status is RemoteStatus.NEVER_RECEIVED
                    else "outcome_unknown",
                )
            error = ToolError.REJECTED if lookup.status is RemoteStatus.PROCESSED_FAILURE else None
            output = (
                validate_output(
                    lookup.output_json or "", invocation.tool_version, invocation.validated_input
                )
                if error is None
                else None
            )
            receipt = ToolReceipt(
                self.ids.tool_receipt_id(),
                invocation.finish(self.clock.now(), error),
                output,
                len(input_json(invocation.validated_input).encode()),
                len((lookup.output_json or "").encode()) if output else 0,
                "observed" if output else "observed_failure",
            )
            self.store.finish_tool_invocation(receipt)
            if self.tools.governance is not None:
                self.tools.governance.consumed(receipt.invocation)
            self._event(run, invocation, EventType.RECOVERY_RECEIPT_RECONCILED, lookup.status.value)
        # Separate committed receipt from parent repair; window D is recoverable.
        self.tools.reconcile_receipt(receipt)
        return RecoveryCase(
            workspace,
            "tool_invocation",
            str(invocation_id),
            RecoveryReason.RESUME_LOCAL,
            "observed_success" if output else "observed_failure",
        )
