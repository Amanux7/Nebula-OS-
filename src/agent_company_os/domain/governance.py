"""Exact immutable intents, bounded policy, and append-only human decisions."""

import json
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, StrEnum
from hashlib import sha256

from agent_company_os.domain.agent import ActionId, AgentRunId
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.ids import ExecutionId, GoalId, OpaqueId, TaskId, Version, WorkspaceId
from agent_company_os.domain.tools import (
    ExecutorKind,
    ToolGrant,
    ToolInvocationId,
    ToolRisk,
    ToolVersion,
)
from agent_company_os.domain.validation import require_utc


class ActionIntentId(OpaqueId):
    pass


class ReviewerId(OpaqueId):
    pass


class AutonomyLevel(IntEnum):
    OBSERVE = 0
    RECOMMEND = 1
    DRAFT = 2
    BOUNDED_EXECUTE = 3
    AUTONOMOUS_WITHIN_POLICY = 4


class ApprovalEffect(StrEnum):
    DENY = "deny"
    REQUIRED = "approval_required"
    ALLOW = "allowed_without_approval"


class DecisionKind(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass(frozen=True)
class ReviewerPrincipal:
    id: ReviewerId
    workspace_id: WorkspaceId

    def __post_init__(self) -> None:
        if (
            not isinstance(self.id, ReviewerId)
            or not isinstance(self.workspace_id, WorkspaceId)
            or len(str(self.id)) > 128
        ):
            raise InvariantViolation("reviewer_principal_schema")


@dataclass(frozen=True)
class ApprovalPolicy:
    workspace_id: WorkspaceId
    version: Version
    tools: tuple[ToolGrant, ...]
    destinations: tuple[str, ...]
    reviewers: tuple[ReviewerPrincipal, ...]
    bounded_execute: bool = False
    enabled: bool = True
    expiry_seconds: int = 30

    def __post_init__(self) -> None:
        if (
            type(self.enabled) is not bool
            or type(self.bounded_execute) is not bool
            or type(self.expiry_seconds) is not int
            or not 1 <= self.expiry_seconds <= 300
            or not isinstance(self.tools, tuple)
            or len(self.tools) > 3
            or not isinstance(self.destinations, tuple)
            or len(self.destinations) > 10
            or not isinstance(self.reviewers, tuple)
            or len(self.reviewers) > 10
            or any(not isinstance(t, ToolGrant) for t in self.tools)
            or any(
                not isinstance(r, ReviewerPrincipal) or r.workspace_id != self.workspace_id
                for r in self.reviewers
            )
            or any(
                not isinstance(d, str) or not d.strip() or len(d) > 128 for d in self.destinations
            )
            or len(set(self.reviewers)) != len(self.reviewers)
        ):
            raise InvariantViolation("approval_policy_bounds")

    def evaluate(self, autonomy: int, tool: ToolVersion, destination: str) -> ApprovalEffect:
        if (
            not self.enabled
            or tool.definition.workspace_id != self.workspace_id
            or tool.grant not in self.tools
            or destination not in self.destinations
            or tool.executor_kind is not ExecutorKind.SEND_FIXTURE_MESSAGE
            or tool.definition.risk is not ToolRisk.EXTERNAL_WRITE
            or autonomy not in (2, 3)
        ):
            return ApprovalEffect.DENY
        if autonomy == 3 and self.bounded_execute:
            return ApprovalEffect.ALLOW
        return ApprovalEffect.REQUIRED


def fingerprint(
    workspace: WorkspaceId,
    actor: AgentRunId,
    action: ActionId,
    tool: ToolVersion,
    arguments_json: str,
) -> str:
    return sha256(
        json.dumps(
            [
                str(workspace),
                str(actor),
                str(action),
                str(tool.definition.id),
                tool.version.value,
                tool.executor_kind.value,
                tool.definition.risk.value,
                arguments_json,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


@dataclass(frozen=True)
class ActionIntent:
    id: ActionIntentId
    workspace_id: WorkspaceId
    run_id: AgentRunId
    action_id: ActionId
    goal_id: GoalId
    task_id: TaskId
    execution_id: ExecutionId
    tool: ToolVersion
    arguments_json: str
    destination: str
    fingerprint: str
    policy: ApprovalPolicy
    effect: ApprovalEffect
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.created_at, "intent_created")
        require_utc(self.expires_at, "intent_expiry")
        if (
            self.expires_at <= self.created_at
            or (self.expires_at - self.created_at).total_seconds() > self.policy.expiry_seconds
            or self.policy.workspace_id != self.workspace_id
            or self.tool.definition.workspace_id != self.workspace_id
            or len(self.arguments_json.encode()) > self.tool.max_input_bytes
            or self.fingerprint
            != fingerprint(
                self.workspace_id, self.run_id, self.action_id, self.tool, self.arguments_json
            )
        ):
            raise InvariantViolation("intent_binding")


@dataclass(frozen=True)
class ApprovalRequest:
    intent_id: ActionIntentId
    fingerprint: str
    expires_at: datetime
    preview: str


@dataclass(frozen=True)
class ApprovalDecision:
    intent_id: ActionIntentId
    fingerprint: str
    policy_version: Version
    kind: DecisionKind
    reviewer: ReviewerPrincipal | None
    at: datetime
    reason: str = ""

    def __post_init__(self) -> None:
        require_utc(self.at, "approval_decision")
        if (
            not isinstance(self.kind, DecisionKind)
            or not isinstance(self.reason, str)
            or len(self.reason) > 256
            or (self.kind is not DecisionKind.EXPIRED and self.reviewer is None)
        ):
            raise InvariantViolation("approval_decision_schema")


@dataclass(frozen=True)
class GovernedAction:
    intent: ActionIntent
    request: ApprovalRequest | None = None
    decisions: tuple[ApprovalDecision, ...] = ()
    cancelled: bool = False
    invocation_id: ToolInvocationId | None = None
    consumed: bool = False
    version: Version = Version(1)

    def __post_init__(self) -> None:
        intent = self.intent
        if (
            not isinstance(self.decisions, tuple)
            or len(self.decisions) > 2
            or type(self.cancelled) is not bool
            or type(self.consumed) is not bool
            or self.consumed
            and self.invocation_id is None
            or (intent.effect is ApprovalEffect.REQUIRED) != (self.request is not None)
        ):
            raise InvariantViolation("governed_action_schema")
        if self.request is not None and (
            self.request.intent_id != intent.id
            or self.request.fingerprint != intent.fingerprint
            or self.request.expires_at != intent.expires_at
            or len(self.request.preview) > 600
        ):
            raise InvariantViolation("approval_request_binding")
        for index, decision in enumerate(self.decisions):
            if (
                self.request is None
                or decision.intent_id != intent.id
                or decision.fingerprint != intent.fingerprint
                or decision.policy_version != intent.policy.version
                or decision.at < intent.created_at
                or decision.kind is DecisionKind.APPROVED
                and decision.at >= intent.expires_at
                or decision.kind is DecisionKind.EXPIRED
                and decision.at < intent.expires_at
                or decision.reviewer is not None
                and decision.reviewer not in intent.policy.reviewers
                or index == 0
                and decision.kind is DecisionKind.REVOKED
                or index == 1
                and (
                    self.decisions[0].kind is not DecisionKind.APPROVED
                    or decision.kind not in (DecisionKind.REVOKED, DecisionKind.EXPIRED)
                    or decision.at < self.decisions[0].at
                )
            ):
                raise InvariantViolation("approval_decision_binding")
