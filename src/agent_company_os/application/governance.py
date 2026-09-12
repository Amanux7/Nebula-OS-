"""Trusted-host review commands; policy never supplies a missing Tool grant."""

from dataclasses import replace
from datetime import timedelta

from agent_company_os.application.organization import AgentRegistry
from agent_company_os.application.tool_validation import input_json
from agent_company_os.domain.agent import AgentRun
from agent_company_os.domain.decisions import Action
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.events import Event, EventType
from agent_company_os.domain.governance import (
    ActionIntent,
    ActionIntentId,
    ApprovalDecision,
    ApprovalEffect,
    ApprovalRequest,
    DecisionKind,
    GovernedAction,
    ReviewerPrincipal,
    fingerprint,
)
from agent_company_os.domain.ids import WorkspaceId
from agent_company_os.domain.tools import FixtureMessageInput, ToolInvocation, ToolVersion
from agent_company_os.domain.transitions import SubjectType
from agent_company_os.ports.clock import Clock
from agent_company_os.ports.ids import IdGenerator
from agent_company_os.ports.runtime_store import RuntimeStore


class GovernanceService:
    def __init__(
        self,
        store: RuntimeStore,
        clock: Clock,
        ids: IdGenerator,
        registry: AgentRegistry | None = None,
    ) -> None:
        self.store, self.clock, self.ids, self.registry = store, clock, ids, registry

    def event(self, record: GovernedAction, kind: EventType, reason: str = "none") -> None:
        intent = record.intent
        run = self.store.get_run(intent.workspace_id, intent.run_id)
        self.store.append_event(
            Event(
                self.ids.event_id(),
                intent.workspace_id,
                kind,
                SubjectType.AGENT_RUN,
                str(run.id),
                run.version,
                self.clock.now(),
                (
                    ("intent_id", str(intent.id)),
                    ("action_id", str(intent.action_id)),
                    ("fingerprint", intent.fingerprint),
                    ("policy_version", str(intent.policy.version.value)),
                    ("risk", intent.tool.definition.risk.value),
                    ("reason", reason),
                ),
            )
        )

    def organization_check(self, run: AgentRun) -> None:
        if run.organization_version is not None:
            if self.registry is None:
                raise InvariantViolation("approval_organization_registry_required")
            snapshot = self.registry.capture(run.workspace_id)
            # Writes are stricter than historical read routing: graph changes invalidate intent use.
            if (
                snapshot.graph.version != run.organization_version
                or run.definition_version not in self.registry.query(run.workspace_id, snapshot)
            ):
                raise InvariantViolation("approval_organization_changed")

    def prepare(
        self, run: AgentRun, action: Action, tool: ToolVersion, request: FixtureMessageInput
    ) -> GovernedAction:
        existing = next(
            (
                g
                for g in self.store.governed_actions(run.workspace_id)
                if g.intent.action_id == action.id
            ),
            None,
        )
        if existing is not None:
            self.validate(existing, run, action, tool, request)
            return existing
        policy = self.store.approval_policy(run.workspace_id)
        if policy is None:
            raise InvariantViolation("approval_policy_missing")
        self.organization_check(run)
        normalized = input_json(request)
        now = self.clock.now()
        intent = ActionIntent(
            ActionIntentId(f"intent:{action.id}"),
            run.workspace_id,
            run.id,
            action.id,
            run.goal_id,
            run.task_id,
            run.execution_id,
            tool,
            normalized,
            request.destination,
            fingerprint(run.workspace_id, run.id, action.id, tool, normalized),
            policy,
            policy.evaluate(run.definition_version.autonomy_ceiling, tool, request.destination),
            now,
            min(run.deadline, now + timedelta(seconds=policy.expiry_seconds)),
        )
        approval = (
            ApprovalRequest(
                intent.id,
                intent.fingerprint,
                intent.expires_at,
                f"{run.definition_version.definition.name[:128]} "
                f"v{run.definition_version.version.value}: {tool.executor_kind.value} "
                f"to {request.destination}; {tool.definition.risk.value}",
            )
            if intent.effect is ApprovalEffect.REQUIRED
            else None
        )
        record = GovernedAction(intent, approval)
        self.store.save_governed_action(record, None)
        self.event(record, EventType.ACTION_INTENT_CREATED)
        if approval:
            self.event(record, EventType.APPROVAL_REQUESTED)
        return record

    def validate(
        self,
        record: GovernedAction,
        run: AgentRun,
        action: Action,
        tool: ToolVersion,
        request: FixtureMessageInput,
    ) -> None:
        intent = record.intent
        if (
            self.store.governed_action(run.workspace_id, intent.id) != record
            or intent.run_id != run.id
            or intent.action_id != action.id
            or intent.tool != tool
            or intent.destination != request.destination
            or intent.arguments_json != input_json(request)
            or intent.fingerprint
            != fingerprint(run.workspace_id, run.id, action.id, tool, input_json(request))
            or intent.policy != self.store.approval_policy(run.workspace_id)
            or tool.grant not in run.definition_version.allowed_tools
            or not run.definition_version.enabled
            or intent.effect
            != intent.policy.evaluate(
                run.definition_version.autonomy_ceiling, tool, request.destination
            )
        ):
            raise InvariantViolation("approval_binding_or_policy_changed")
        self.organization_check(run)

    def allowed(self, record: GovernedAction) -> bool:
        if record.cancelled or record.invocation_id is not None or record.consumed:
            return False
        if self.clock.now() >= record.intent.expires_at:
            return False
        if record.intent.effect is ApprovalEffect.ALLOW:
            return True
        return (
            record.intent.effect is ApprovalEffect.REQUIRED
            and bool(record.decisions)
            and record.decisions[-1].kind is DecisionKind.APPROVED
        )

    def decide(
        self,
        workspace: WorkspaceId,
        intent_id: ActionIntentId,
        digest: str,
        reviewer: ReviewerPrincipal,
        kind: DecisionKind,
        reason: str = "",
    ) -> GovernedAction:
        with self.store.atomic():
            record = self.store.governed_action(workspace, intent_id)
            policy = self.store.approval_policy(workspace)
            if (
                policy is None
                or reviewer not in policy.reviewers
                or reviewer not in record.intent.policy.reviewers
                or reviewer.workspace_id != workspace
            ):
                raise InvariantViolation("reviewer_not_authorized")
            if (
                record.request is None
                or digest != record.intent.fingerprint
                or record.intent.policy != policy
                or record.cancelled
                or record.invocation_id is not None
                or self.clock.now() >= record.intent.expires_at
                or kind not in (DecisionKind.APPROVED, DecisionKind.REJECTED, DecisionKind.REVOKED)
                or (
                    kind is DecisionKind.REVOKED
                    and (
                        not record.decisions
                        or record.decisions[-1].kind is not DecisionKind.APPROVED
                    )
                )
                or (kind is not DecisionKind.REVOKED and bool(record.decisions))
            ):
                raise InvariantViolation("approval_decision_not_available")
            decision = ApprovalDecision(
                intent_id, digest, policy.version, kind, reviewer, self.clock.now(), reason
            )
            updated = replace(
                record, decisions=(*record.decisions, decision), version=record.version.next()
            )
            self.store.save_governed_action(updated, record.version)
            self.event(
                updated,
                {
                    DecisionKind.APPROVED: EventType.APPROVAL_GRANTED,
                    DecisionKind.REJECTED: EventType.APPROVAL_REJECTED,
                    DecisionKind.REVOKED: EventType.APPROVAL_REVOKED,
                }[kind],
            )
            return updated

    def cancel(self, workspace: WorkspaceId, intent_id: ActionIntentId) -> GovernedAction:
        with self.store.atomic():
            record = self.store.governed_action(workspace, intent_id)
            if record.cancelled or record.invocation_id is not None:
                raise InvariantViolation("intent_already_cancelled_or_claimed")
            updated = replace(record, cancelled=True, version=record.version.next())
            self.store.save_governed_action(updated, record.version)
            self.event(updated, EventType.ACTION_INTENT_CANCELLED)
            return updated

    def expire(self, workspace: WorkspaceId, intent_id: ActionIntentId) -> GovernedAction:
        with self.store.atomic():
            record = self.store.governed_action(workspace, intent_id)
            if (
                record.request
                and not record.cancelled
                and record.invocation_id is None
                and self.clock.now() >= record.intent.expires_at
                and (not record.decisions or record.decisions[-1].kind is DecisionKind.APPROVED)
            ):
                decision = ApprovalDecision(
                    intent_id,
                    record.intent.fingerprint,
                    record.intent.policy.version,
                    DecisionKind.EXPIRED,
                    None,
                    self.clock.now(),
                )
                updated = replace(
                    record, decisions=(*record.decisions, decision), version=record.version.next()
                )
                self.store.save_governed_action(updated, record.version)
                self.event(updated, EventType.APPROVAL_EXPIRED)
                return updated
            return record

    def claim(self, record: GovernedAction, invocation: ToolInvocation) -> None:
        if not self.allowed(record):
            raise InvariantViolation("approval_not_executable")
        updated = replace(record, invocation_id=invocation.id, version=record.version.next())
        self.store.save_governed_action(updated, record.version)
        self.event(updated, EventType.ACTION_EXECUTION_AUTHORIZED)

    def consumed(self, invocation: ToolInvocation) -> None:
        record = next(
            (
                g
                for g in self.store.governed_actions(invocation.workspace_id)
                if g.invocation_id == invocation.id
            ),
            None,
        )
        if record is not None and record.request is not None:
            updated = replace(record, consumed=True, version=record.version.next())
            self.store.save_governed_action(updated, record.version)
            self.event(updated, EventType.APPROVAL_CONSUMED)
