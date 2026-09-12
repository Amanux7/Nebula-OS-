"""Bounded point-to-point agent communication; messages never transfer authority."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from agent_company_os.domain.agent import AgentDefinitionId, AgentRunId
from agent_company_os.domain.errors import InvalidStateTransition, InvariantViolation
from agent_company_os.domain.ids import OpaqueId, TaskId, Version, WorkspaceId
from agent_company_os.domain.orchestration import (
    AgentRequirements,
    DelegationId,
    OrchestrationRunId,
)
from agent_company_os.domain.validation import clean_required_text, require_utc


class AgentMessageId(OpaqueId):
    pass


class MessageThreadId(OpaqueId):
    pass


class HandoffId(OpaqueId):
    pass


class MessageKind(StrEnum):
    INFORMATION = "information"
    REQUEST = "request"
    RESPONSE = "response"
    HANDOFF_REQUEST = "handoff_request"
    HANDOFF_ACCEPT = "handoff_accept"
    HANDOFF_REJECT = "handoff_reject"
    HANDOFF_RESULT = "handoff_result"


class MessageStatus(StrEnum):
    CREATED = "created"
    DELIVERED = "delivered"
    CONSUMED = "consumed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class ThreadStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class HandoffStatus(StrEnum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class ReferenceKind(StrEnum):
    TASK_RESULT = "task_result"
    TOOL_RECEIPT = "tool_receipt"
    EVIDENCE_PACK = "evidence_pack"
    MEMORY_CONTEXT_PACK = "memory_context_pack"


@dataclass(frozen=True)
class CommunicationPolicy:
    max_message_chars: int = 2000
    max_payload_items: int = 10
    max_references: int = 8
    max_messages_per_thread: int = 20
    max_messages_per_agent_run: int = 20
    max_messages_per_run: int = 50
    max_handoff_depth: int = 2
    max_handoffs_per_task: int = 2
    max_requests_per_task: int = 5
    max_context_messages: int = 5
    response_timeout_seconds: int = 300
    allowed_kinds: tuple[MessageKind, ...] = tuple(MessageKind)
    allowed_reference_kinds: tuple[ReferenceKind, ...] = tuple(ReferenceKind)
    allowed_recipient_roles: tuple[str, ...] = ()
    version: str = "bounded-communication-v1"

    def __post_init__(self) -> None:
        bounds = (
            (self.max_message_chars, 8000),
            (self.max_payload_items, 25),
            (self.max_references, 20),
            (self.max_messages_per_thread, 100),
            (self.max_messages_per_agent_run, 100),
            (self.max_messages_per_run, 250),
            (self.max_handoff_depth, 5),
            (self.max_handoffs_per_task, 10),
            (self.max_requests_per_task, 25),
            (self.max_context_messages, 20),
            (self.response_timeout_seconds, 3600),
        )
        if any(type(value) is not int or not 1 <= value <= hard for value, hard in bounds):
            raise InvariantViolation("communication_policy_bounds")
        for items, kind in (
            (self.allowed_kinds, MessageKind),
            (self.allowed_reference_kinds, ReferenceKind),
        ):
            if (
                not items
                or len(set(items)) != len(items)
                or any(not isinstance(i, kind) for i in items)
            ):
                raise InvariantViolation("communication_policy_allowlist")
        if len(set(self.allowed_recipient_roles)) != len(self.allowed_recipient_roles) or any(
            not role or len(role) > 64 for role in self.allowed_recipient_roles
        ):
            raise InvariantViolation("communication_role_allowlist")
        clean_required_text(self.version, "communication_policy_version")


@dataclass(frozen=True)
class InformationPayload:
    summary: str
    items: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _payload_text(self.summary, self.items)


@dataclass(frozen=True)
class RequestPayload:
    request_type: str
    question: str
    expected_response: str
    substantial_work: bool = False

    def __post_init__(self) -> None:
        _payload_text(self.request_type, (self.question, self.expected_response))
        if type(self.substantial_work) is not bool:
            raise InvariantViolation("request_substantial_work_boolean")


@dataclass(frozen=True)
class ResponsePayload:
    summary: str
    items: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _payload_text(self.summary, self.items)


@dataclass(frozen=True)
class HandoffRequestPayload:
    reason_code: str
    summary: str
    target_requirements: AgentRequirements

    def __post_init__(self) -> None:
        _payload_text(self.reason_code, (self.summary,))


@dataclass(frozen=True)
class HandoffResultPayload:
    summary: str
    task_result_reference: str

    def __post_init__(self) -> None:
        _payload_text(self.summary, (self.task_result_reference,))


type MessagePayload = (
    InformationPayload
    | RequestPayload
    | ResponsePayload
    | HandoffRequestPayload
    | HandoffResultPayload
)


def _payload_text(primary: str, items: tuple[str, ...]) -> None:
    clean_required_text(primary, "message_payload")
    if (
        len(primary) > 2000
        or not isinstance(items, tuple)
        or len(items) > 25
        or any(not isinstance(item, str) or not item.strip() or len(item) > 2000 for item in items)
    ):
        raise InvariantViolation("message_payload_bounds")


def payload_chars(payload: MessagePayload) -> int:
    if isinstance(payload, (InformationPayload, ResponsePayload)):
        return len(payload.summary) + sum(len(item) for item in payload.items)
    if isinstance(payload, RequestPayload):
        return len(payload.request_type) + len(payload.question) + len(payload.expected_response)
    if isinstance(payload, HandoffRequestPayload):
        return len(payload.reason_code) + len(payload.summary)
    return len(payload.summary) + len(payload.task_result_reference)


def payload_item_count(payload: MessagePayload) -> int:
    if isinstance(payload, (InformationPayload, ResponsePayload)):
        return len(payload.items)
    return 1


@dataclass(frozen=True)
class CommunicationReference:
    kind: ReferenceKind
    reference_id: str
    workspace_id: WorkspaceId
    source_agent_run_id: AgentRunId

    def __post_init__(self) -> None:
        clean_required_text(self.reference_id, "communication_reference")
        if len(self.reference_id) > 256:
            raise InvariantViolation("communication_reference_bound")


@dataclass(frozen=True)
class MessageThread:
    id: MessageThreadId
    workspace_id: WorkspaceId
    orchestration_run_id: OrchestrationRunId
    subject: str
    created_by: AgentRunId
    created_at: datetime
    status: ThreadStatus = ThreadStatus.OPEN
    version: Version = Version(1)

    def __post_init__(self) -> None:
        clean_required_text(self.subject, "message_thread_subject")
        require_utc(self.created_at, "created_at")
        if len(self.subject) > 160:
            raise InvariantViolation("message_thread_subject_bound")


@dataclass(frozen=True)
class AgentMessage:
    id: AgentMessageId
    workspace_id: WorkspaceId
    orchestration_run_id: OrchestrationRunId
    thread_id: MessageThreadId
    sender_agent_run_id: AgentRunId
    sender_definition_id: AgentDefinitionId
    sender_definition_version: Version
    recipient_agent_run_id: AgentRunId
    recipient_definition_id: AgentDefinitionId
    recipient_definition_version: Version
    sender_task_id: TaskId
    sender_delegation_id: DelegationId
    recipient_task_id: TaskId
    recipient_delegation_id: DelegationId
    kind: MessageKind
    payload: MessagePayload
    references: tuple[CommunicationReference, ...]
    correlation_id: str
    created_at: datetime
    deadline: datetime
    policy_version: str
    in_reply_to: AgentMessageId | None = None
    status: MessageStatus = MessageStatus.CREATED
    version: Version = Version(1)
    delivered_at: datetime | None = None
    ended_at: datetime | None = None
    status_reason: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        require_utc(self.created_at, "created_at")
        require_utc(self.deadline, "deadline")
        clean_required_text(self.correlation_id, "message_correlation_id")
        clean_required_text(self.policy_version, "communication_policy_version")
        expected = {
            MessageKind.INFORMATION: InformationPayload,
            MessageKind.REQUEST: RequestPayload,
            MessageKind.RESPONSE: ResponsePayload,
            MessageKind.HANDOFF_REQUEST: HandoffRequestPayload,
            MessageKind.HANDOFF_ACCEPT: InformationPayload,
            MessageKind.HANDOFF_REJECT: InformationPayload,
            MessageKind.HANDOFF_RESULT: HandoffResultPayload,
        }[self.kind]
        if (
            self.schema_version != 1
            or self.deadline <= self.created_at
            or len(self.correlation_id) > 128
            or not isinstance(self.references, tuple)
            or len(self.references) > 20
            or len(set((ref.kind, ref.reference_id) for ref in self.references))
            != len(self.references)
            or not isinstance(self.payload, expected)
        ):
            raise InvariantViolation("agent_message_schema")
        terminal = self.status in {
            MessageStatus.CONSUMED,
            MessageStatus.REJECTED,
            MessageStatus.CANCELLED,
            MessageStatus.TIMED_OUT,
        }
        if (
            self.status in {MessageStatus.DELIVERED, MessageStatus.CONSUMED}
            and self.delivered_at is None
        ):
            raise InvariantViolation("message_delivery_time")
        if (
            self.status in {MessageStatus.CREATED, MessageStatus.REJECTED}
            and self.delivered_at is not None
        ):
            raise InvariantViolation("message_delivery_time")
        if terminal != (self.ended_at is not None):
            raise InvariantViolation("message_terminal_time")
        if (
            self.status
            in {MessageStatus.REJECTED, MessageStatus.CANCELLED, MessageStatus.TIMED_OUT}
        ) != bool(self.status_reason):
            raise InvariantViolation("message_status_reason")

    def evolve(
        self, status: MessageStatus, at: datetime, reason: str | None = None
    ) -> AgentMessage:
        allowed = {
            MessageStatus.CREATED: {
                MessageStatus.DELIVERED,
                MessageStatus.REJECTED,
                MessageStatus.CANCELLED,
                MessageStatus.TIMED_OUT,
            },
            MessageStatus.DELIVERED: {
                MessageStatus.CONSUMED,
                MessageStatus.CANCELLED,
                MessageStatus.TIMED_OUT,
            },
        }
        if status not in allowed.get(self.status, set()):
            raise InvalidStateTransition("AgentMessage", str(self.id), self.status, status)
        require_utc(at, "message_status_time")
        terminal = status in {
            MessageStatus.CONSUMED,
            MessageStatus.REJECTED,
            MessageStatus.CANCELLED,
            MessageStatus.TIMED_OUT,
        }
        return replace(
            self,
            status=status,
            version=self.version.next(),
            delivered_at=at if status is MessageStatus.DELIVERED else self.delivered_at,
            ended_at=at if terminal else None,
            status_reason=reason,
        )


@dataclass(frozen=True)
class HandoffRequest:
    id: HandoffId
    workspace_id: WorkspaceId
    orchestration_run_id: OrchestrationRunId
    sender_agent_run_id: AgentRunId
    sender_definition_id: AgentDefinitionId
    sender_definition_version: Version
    source_task_id: TaskId
    source_delegation_id: DelegationId
    payload: HandoffRequestPayload
    references: tuple[CommunicationReference, ...]
    depth: int
    created_at: datetime
    deadline: datetime
    policy_version: str
    parent_handoff_id: HandoffId | None = None
    status: HandoffStatus = HandoffStatus.REQUESTED
    version: Version = Version(1)
    recipient_definition_id: AgentDefinitionId | None = None
    recipient_definition_version: Version | None = None
    resulting_delegation_id: DelegationId | None = None
    result_reference: str | None = None
    ended_at: datetime | None = None
    status_reason: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        require_utc(self.created_at, "created_at")
        require_utc(self.deadline, "deadline")
        if (
            self.schema_version != 1
            or self.deadline <= self.created_at
            or not 1 <= self.depth <= 5
            or len(self.references) > 20
            or (self.recipient_definition_id is None) != (self.recipient_definition_version is None)
        ):
            raise InvariantViolation("handoff_schema")
        requires_delegation = self.status in {
            HandoffStatus.ACCEPTED,
            HandoffStatus.COMPLETED,
        }
        forbids_delegation = self.status in {
            HandoffStatus.REQUESTED,
            HandoffStatus.REJECTED,
        }
        if (
            requires_delegation
            and self.resulting_delegation_id is None
            or (forbids_delegation and self.resulting_delegation_id is not None)
        ):
            raise InvariantViolation("handoff_delegation_binding")
        if (self.status is HandoffStatus.COMPLETED) != bool(self.result_reference):
            raise InvariantViolation("handoff_result_binding")
        terminal = self.status in {
            HandoffStatus.REJECTED,
            HandoffStatus.COMPLETED,
            HandoffStatus.FAILED,
            HandoffStatus.TIMED_OUT,
            HandoffStatus.CANCELLED,
        }
        if terminal != (self.ended_at is not None):
            raise InvariantViolation("handoff_terminal_time")
        if (
            self.status
            in {
                HandoffStatus.REJECTED,
                HandoffStatus.FAILED,
                HandoffStatus.TIMED_OUT,
                HandoffStatus.CANCELLED,
            }
            and not self.status_reason
        ):
            raise InvariantViolation("handoff_status_reason")

    def accept(
        self,
        definition_id: AgentDefinitionId,
        definition_version: Version,
        delegation_id: DelegationId,
    ) -> HandoffRequest:
        if self.status is not HandoffStatus.REQUESTED:
            raise InvalidStateTransition("HandoffRequest", str(self.id), self.status, "accept")
        return replace(
            self,
            status=HandoffStatus.ACCEPTED,
            version=self.version.next(),
            recipient_definition_id=definition_id,
            recipient_definition_version=definition_version,
            resulting_delegation_id=delegation_id,
        )

    def finish(
        self,
        status: HandoffStatus,
        at: datetime,
        *,
        reason: str | None = None,
        result: str | None = None,
    ) -> HandoffRequest:
        allowed = {
            HandoffStatus.REQUESTED: {
                HandoffStatus.REJECTED,
                HandoffStatus.TIMED_OUT,
                HandoffStatus.CANCELLED,
            },
            HandoffStatus.ACCEPTED: {
                HandoffStatus.COMPLETED,
                HandoffStatus.FAILED,
                HandoffStatus.TIMED_OUT,
                HandoffStatus.CANCELLED,
            },
        }
        if status not in allowed.get(self.status, set()):
            raise InvalidStateTransition("HandoffRequest", str(self.id), self.status, status)
        require_utc(at, "handoff_status_time")
        return replace(
            self,
            status=status,
            version=self.version.next(),
            result_reference=result,
            ended_at=at,
            status_reason=reason,
        )


@dataclass(frozen=True)
class MessageContextItem:
    message_id: AgentMessageId
    sender_agent_run_id: AgentRunId
    sender_definition_id: AgentDefinitionId
    sender_definition_version: Version
    kind: MessageKind
    payload: MessagePayload
    references: tuple[CommunicationReference, ...]
    correlation_id: str
    created_at: datetime
    trust: str = "untrusted_agent_message"


@dataclass(frozen=True)
class AgentMessageContext:
    workspace_id: WorkspaceId
    recipient_agent_run_id: AgentRunId
    messages: tuple[MessageContextItem, ...]
    policy_version: str
    captured_at: datetime
    schema_version: int = 1

    def __post_init__(self) -> None:
        require_utc(self.captured_at, "captured_at")
        if self.schema_version != 1 or len(self.messages) > 20:
            raise InvariantViolation("message_context_bound")
