"""Governed point-to-point delivery and orchestration-mediated handoffs."""

from __future__ import annotations

from datetime import timedelta

from agent_company_os.application.orchestration import OrchestrationService
from agent_company_os.domain.agent import (
    AgentDefinitionVersion,
    AgentRun,
    AgentRunId,
    AgentRunStatus,
)
from agent_company_os.domain.communication import (
    AgentMessage,
    AgentMessageContext,
    AgentMessageId,
    CommunicationPolicy,
    CommunicationReference,
    HandoffId,
    HandoffRequest,
    HandoffRequestPayload,
    HandoffStatus,
    MessageContextItem,
    MessageKind,
    MessagePayload,
    MessageStatus,
    MessageThread,
    MessageThreadId,
    ReferenceKind,
    RequestPayload,
    payload_chars,
    payload_item_count,
)
from agent_company_os.domain.errors import EntityNotFound, InvariantViolation, VersionConflict
from agent_company_os.domain.events import Event, EventType
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.knowledge import EvidencePackId
from agent_company_os.domain.memory import MemoryContextPackId, MemoryEntryStatus
from agent_company_os.domain.orchestration import (
    Delegation,
    DelegationId,
    OrchestrationRun,
    OrchestrationRunId,
    OrchestrationStatus,
    TaskResultReference,
)
from agent_company_os.domain.organization import RouteKind
from agent_company_os.domain.transitions import SubjectType
from agent_company_os.ports.clock import Clock
from agent_company_os.ports.communication import CommunicationStore
from agent_company_os.ports.ids import IdGenerator
from agent_company_os.ports.knowledge import KnowledgeStore
from agent_company_os.ports.memory import MemoryStore


class AgentCommunicationService:
    def __init__(
        self,
        store: CommunicationStore,
        orchestration: OrchestrationService,
        clock: Clock,
        ids: IdGenerator,
        *,
        knowledge: KnowledgeStore | None = None,
        memory: MemoryStore | None = None,
    ) -> None:
        self.store = store
        self.orchestration = orchestration
        self.clock = clock
        self.ids = ids
        self.knowledge = knowledge
        self.memory = memory

    @staticmethod
    def _version(entity: object, actual: Version, expected: Version, name: str) -> None:
        if actual != expected:
            raise VersionConflict(name, str(entity), expected.value, actual.value)

    def create_thread(
        self,
        workspace_id: WorkspaceId,
        orchestration_run_id: OrchestrationRunId,
        created_by: AgentRunId,
        subject: str,
        *,
        thread_id: MessageThreadId | None = None,
    ) -> MessageThread:
        with self.store.atomic():
            run = self.store.orchestration.run(workspace_id, orchestration_run_id)
            creator = self.store.orchestration.runtime.get_run(workspace_id, created_by)
            if creator.goal_id != run.goal_id or run.status not in {
                OrchestrationStatus.RUNNING,
                OrchestrationStatus.WAITING,
            }:
                raise InvariantViolation("thread_creator_scope")
            thread = MessageThread(
                thread_id or self.ids.message_thread_id(),
                workspace_id,
                run.id,
                subject,
                creator.id,
                self.clock.now(),
            )
            self.store.add_thread(thread)
            return thread

    def send(
        self,
        workspace_id: WorkspaceId,
        orchestration_run_id: OrchestrationRunId,
        thread_id: MessageThreadId,
        sender_agent_run_id: AgentRunId,
        recipient_agent_run_id: AgentRunId,
        kind: MessageKind,
        payload: MessagePayload,
        references: tuple[CommunicationReference, ...],
        correlation_id: str,
        policy: CommunicationPolicy,
        *,
        sender_expected: Version,
        recipient_expected: Version,
        orchestration_expected: Version,
        in_reply_to: AgentMessageId | None = None,
        message_id: AgentMessageId | None = None,
        schema_version: int = 1,
    ) -> AgentMessage:
        identifier = message_id or self.ids.agent_message_id()
        try:
            return self.store.message(workspace_id, identifier)
        except EntityNotFound:
            pass
        with self.store.atomic():
            orchestration = self.store.orchestration.run(workspace_id, orchestration_run_id)
            self._version(
                orchestration.id, orchestration.version, orchestration_expected, "OrchestrationRun"
            )
            thread = self.store.thread(workspace_id, thread_id)
            sender = self.store.orchestration.runtime.get_run(workspace_id, sender_agent_run_id)
            recipient = self.store.orchestration.runtime.get_run(
                workspace_id, recipient_agent_run_id
            )
            self._version(sender.id, sender.version, sender_expected, "AgentRun")
            self._version(recipient.id, recipient.version, recipient_expected, "AgentRun")
            self._validate_participants(orchestration, thread, sender, recipient, policy)
            self._validate_payload(kind, payload, references, policy, schema_version)
            self._validate_correlation(
                workspace_id,
                thread,
                sender,
                recipient,
                kind,
                correlation_id,
                in_reply_to,
            )
            self._validate_budgets(
                workspace_id, orchestration_run_id, thread_id, sender, kind, policy
            )
            self._authorize_references(
                workspace_id, orchestration_run_id, sender, recipient.definition_version, references
            )
            sender_delegation = self._delegation_for_agent(
                workspace_id, orchestration_run_id, sender
            )
            recipient_delegation = self._delegation_for_agent(
                workspace_id, orchestration_run_id, recipient
            )
            now = self.clock.now()
            message = AgentMessage(
                identifier,
                workspace_id,
                orchestration_run_id,
                thread_id,
                sender.id,
                sender.definition_version.definition.id,
                sender.definition_version.version,
                recipient.id,
                recipient.definition_version.definition.id,
                recipient.definition_version.version,
                sender.task_id,
                sender_delegation.id,
                recipient.task_id,
                recipient_delegation.id,
                kind,
                payload,
                references,
                correlation_id,
                now,
                now + timedelta(seconds=policy.response_timeout_seconds),
                policy.version,
                in_reply_to=in_reply_to,
                schema_version=schema_version,
            )
            self.store.add_message(message)
            self._message_event(message, EventType.AGENT_MESSAGE_CREATED)
            delivered = message.evolve(MessageStatus.DELIVERED, now)
            self.store.save_message(delivered, message.version)
            self._message_event(delivered, EventType.AGENT_MESSAGE_DELIVERED)
            return delivered

    def consume(
        self,
        workspace_id: WorkspaceId,
        message_id: AgentMessageId,
        recipient_expected: Version,
        message_expected: Version,
    ) -> AgentMessage:
        with self.store.atomic():
            message = self.store.message(workspace_id, message_id)
            self._version(message.id, message.version, message_expected, "AgentMessage")
            recipient = self.store.orchestration.runtime.get_run(
                workspace_id, message.recipient_agent_run_id
            )
            self._version(recipient.id, recipient.version, recipient_expected, "AgentRun")
            if recipient.status not in {AgentRunStatus.RUNNING, AgentRunStatus.WAITING}:
                raise InvariantViolation("recipient_unavailable")
            consumed = message.evolve(MessageStatus.CONSUMED, self.clock.now())
            self.store.save_message(consumed, message.version)
            self._message_event(consumed, EventType.AGENT_MESSAGE_CONSUMED)
            return consumed

    def context_for(self, run: AgentRun) -> AgentMessageContext | None:
        messages = tuple(
            item
            for item in self.store.messages_for_agent(run.workspace_id, run.id)
            if item.recipient_agent_run_id == run.id
            and item.status in {MessageStatus.DELIVERED, MessageStatus.CONSUMED}
        )
        if not messages:
            return None
        policy = CommunicationPolicy()
        selected = messages[-policy.max_context_messages :]
        return AgentMessageContext(
            run.workspace_id,
            run.id,
            tuple(
                MessageContextItem(
                    item.id,
                    item.sender_agent_run_id,
                    item.sender_definition_id,
                    item.sender_definition_version,
                    item.kind,
                    item.payload,
                    item.references,
                    item.correlation_id,
                    item.created_at,
                )
                for item in selected
            ),
            selected[-1].policy_version,
            self.clock.now(),
        )

    def expire(self, workspace_id: WorkspaceId, orchestration_run_id: OrchestrationRunId) -> int:
        expired = 0
        with self.store.atomic():
            for message in self.store.messages_for_run(workspace_id, orchestration_run_id):
                if (
                    message.status is MessageStatus.DELIVERED
                    and self.clock.now() >= message.deadline
                ):
                    timed = message.evolve(MessageStatus.TIMED_OUT, self.clock.now(), "timeout")
                    self.store.save_message(timed, message.version)
                    self._message_event(timed, EventType.COMMUNICATION_TIMEOUT)
                    expired += 1
            for handoff in self.store.handoffs_for_run(workspace_id, orchestration_run_id):
                if (
                    handoff.status in {HandoffStatus.REQUESTED, HandoffStatus.ACCEPTED}
                    and self.clock.now() >= handoff.deadline
                ):
                    timed_handoff = handoff.finish(
                        HandoffStatus.TIMED_OUT, self.clock.now(), reason="timeout"
                    )
                    self.store.save_handoff(timed_handoff, handoff.version)
                    self._handoff_event(timed_handoff, EventType.COMMUNICATION_TIMEOUT)
                    expired += 1
        return expired

    def request_handoff(
        self,
        workspace_id: WorkspaceId,
        orchestration_run_id: OrchestrationRunId,
        sender_agent_run_id: AgentRunId,
        source_delegation_id: DelegationId,
        payload: HandoffRequestPayload,
        references: tuple[CommunicationReference, ...],
        policy: CommunicationPolicy,
        *,
        sender_expected: Version,
        orchestration_expected: Version,
        parent_handoff_id: HandoffId | None = None,
        handoff_id: HandoffId | None = None,
        schema_version: int = 1,
    ) -> HandoffRequest:
        with self.store.atomic():
            orchestration = self.store.orchestration.run(workspace_id, orchestration_run_id)
            self._version(
                orchestration.id, orchestration.version, orchestration_expected, "OrchestrationRun"
            )
            sender = self.store.orchestration.runtime.get_run(workspace_id, sender_agent_run_id)
            self._version(sender.id, sender.version, sender_expected, "AgentRun")
            delegation = self.store.orchestration.delegation(workspace_id, source_delegation_id)
            if (
                sender.status not in {AgentRunStatus.RUNNING, AgentRunStatus.WAITING}
                or delegation.orchestration_run_id != orchestration.id
                or delegation.task_id != sender.task_id
                or not sender.definition_version.communication_enabled
            ):
                raise InvariantViolation("handoff_sender_binding")
            prior = tuple(
                item
                for item in self.store.handoffs_for_run(workspace_id, orchestration.id)
                if item.source_task_id == sender.task_id
            )
            if len(prior) >= policy.max_handoffs_per_task:
                raise InvariantViolation("handoff_task_limit")
            depth = 1
            if parent_handoff_id is not None:
                parent = self.store.handoff(workspace_id, parent_handoff_id)
                if parent.source_task_id != sender.task_id:
                    raise InvariantViolation("handoff_parent_scope")
                depth = parent.depth + 1
            if depth > policy.max_handoff_depth:
                raise InvariantViolation("handoff_limit_exceeded")
            self._validate_payload(
                MessageKind.HANDOFF_REQUEST, payload, references, policy, schema_version
            )
            self._authorize_sender_references(workspace_id, orchestration.id, sender, references)
            now = self.clock.now()
            handoff = HandoffRequest(
                handoff_id or self.ids.handoff_id(),
                workspace_id,
                orchestration.id,
                sender.id,
                sender.definition_version.definition.id,
                sender.definition_version.version,
                sender.task_id,
                delegation.id,
                payload,
                references,
                depth,
                now,
                now + timedelta(seconds=policy.response_timeout_seconds),
                policy.version,
                parent_handoff_id=parent_handoff_id,
                schema_version=schema_version,
            )
            self.store.add_handoff(handoff)
            self._handoff_event(handoff, EventType.HANDOFF_REQUESTED)
            return handoff

    def resolve_handoff(
        self,
        workspace_id: WorkspaceId,
        handoff_id: HandoffId,
        handoff_expected: Version,
        orchestration_expected: Version,
        policy: CommunicationPolicy,
    ) -> HandoffRequest:
        with self.store.atomic():
            handoff = self.store.handoff(workspace_id, handoff_id)
            self._version(handoff.id, handoff.version, handoff_expected, "HandoffRequest")
            orchestration = self.store.orchestration.run(workspace_id, handoff.orchestration_run_id)
            self._version(
                orchestration.id, orchestration.version, orchestration_expected, "OrchestrationRun"
            )
            if handoff.status is not HandoffStatus.REQUESTED:
                raise InvariantViolation("handoff_resolution_status")
            if self.clock.now() >= handoff.deadline:
                timed = handoff.finish(HandoffStatus.TIMED_OUT, self.clock.now(), reason="timeout")
                self.store.save_handoff(timed, handoff.version)
                self._handoff_event(timed, EventType.COMMUNICATION_TIMEOUT)
                return timed
            sender = self.store.orchestration.runtime.get_run(
                workspace_id, handoff.sender_agent_run_id
            )
            excluded = self._handoff_lineage_definitions(workspace_id, handoff)
            try:
                selected = self.orchestration.select_agent(
                    orchestration,
                    handoff.payload.target_requirements,
                    candidates=self.orchestration.candidates_for_task(
                        orchestration, handoff.source_task_id
                    ),
                    excluded=excluded,
                    sources=(sender.definition_version,),
                    route_kind=RouteKind.HANDOFF,
                )
                self.orchestration.require_organization_route(
                    orchestration, sender.definition_version, selected, RouteKind.HANDOFF
                )
                self.orchestration.require_organization_route(
                    orchestration, sender.definition_version, selected, RouteKind.DELEGATE
                )
                self._validate_definition_pair(sender.definition_version, selected, policy)
                self._authorize_references(
                    workspace_id,
                    orchestration.id,
                    sender,
                    selected,
                    handoff.references,
                )
            except InvariantViolation as error:
                rejected = handoff.finish(
                    HandoffStatus.REJECTED,
                    self.clock.now(),
                    reason=str(error.details.get("rule", "handoff_not_allowed")),
                )
                self.store.save_handoff(rejected, handoff.version)
                self._handoff_event(rejected, EventType.HANDOFF_REJECTED)
                return rejected
            self.orchestration.runtime.yield_for_handoff(workspace_id, sender.id, sender.version)
            current = self.store.orchestration.run(workspace_id, orchestration.id)
            if current.status is OrchestrationStatus.WAITING:
                running = current.evolve(
                    at=self.clock.now(),
                    status=OrchestrationStatus.RUNNING,
                    escalation_reason=None,
                )
                self.store.orchestration.save_run(running, current.version)
                current = running
            delegation = self.orchestration.delegate(
                workspace_id,
                current.id,
                handoff.source_task_id,
                current.version,
                mode="redelegate",
                target_definition=selected,
            )
            if delegation is None:
                raise InvariantViolation("handoff_delegation_failed")
            accepted = handoff.accept(selected.definition.id, selected.version, delegation.id)
            self.store.save_handoff(accepted, handoff.version)
            self._handoff_event(accepted, EventType.HANDOFF_ACCEPTED)
            return accepted

    def complete_handoff(
        self,
        workspace_id: WorkspaceId,
        handoff_id: HandoffId,
        expected: Version,
    ) -> HandoffRequest:
        with self.store.atomic():
            handoff = self.store.handoff(workspace_id, handoff_id)
            self._version(handoff.id, handoff.version, expected, "HandoffRequest")
            if (
                handoff.status is not HandoffStatus.ACCEPTED
                or handoff.resulting_delegation_id is None
            ):
                raise InvariantViolation("handoff_completion_status")
            attempts = self.store.orchestration.attempts(
                workspace_id, handoff.resulting_delegation_id
            )
            if not attempts:
                raise InvariantViolation("handoff_result_unavailable")
            attempt = attempts[-1]
            run = self.store.orchestration.runtime.get_run(workspace_id, attempt.agent_run_id)
            if run.status is not AgentRunStatus.SUCCEEDED or run.result is None:
                raise InvariantViolation("handoff_result_unavailable")
            reference = TaskResultReference(
                run.task_id,
                attempt.task_attempt_id,
                run.id,
                run.version,
                run.result.source_references,
            ).reference
            completed = handoff.finish(HandoffStatus.COMPLETED, self.clock.now(), result=reference)
            self.store.save_handoff(completed, handoff.version)
            self._handoff_event(completed, EventType.HANDOFF_COMPLETED)
            return completed

    def reject_handoff(
        self, workspace_id: WorkspaceId, handoff_id: HandoffId, expected: Version, reason: str
    ) -> HandoffRequest:
        with self.store.atomic():
            handoff = self.store.handoff(workspace_id, handoff_id)
            self._version(handoff.id, handoff.version, expected, "HandoffRequest")
            rejected = handoff.finish(HandoffStatus.REJECTED, self.clock.now(), reason=reason)
            self.store.save_handoff(rejected, handoff.version)
            self._handoff_event(rejected, EventType.HANDOFF_REJECTED)
            return rejected

    def _validate_participants(
        self,
        orchestration: OrchestrationRun,
        thread: MessageThread,
        sender: AgentRun,
        recipient: AgentRun,
        policy: CommunicationPolicy,
    ) -> None:
        if (
            orchestration.status not in {OrchestrationStatus.RUNNING, OrchestrationStatus.WAITING}
            or thread.orchestration_run_id != orchestration.id
            or sender.goal_id != orchestration.goal_id
            or recipient.goal_id != orchestration.goal_id
            or sender.id == recipient.id
            or sender.status not in {AgentRunStatus.RUNNING, AgentRunStatus.WAITING}
            or recipient.status not in {AgentRunStatus.RUNNING, AgentRunStatus.WAITING}
        ):
            raise InvariantViolation("recipient_unavailable_or_scope_mismatch")
        self._validate_definition_pair(
            sender.definition_version, recipient.definition_version, policy
        )
        self.orchestration.require_organization_route(
            orchestration,
            sender.definition_version,
            recipient.definition_version,
            RouteKind.MESSAGE,
        )
        self._delegation_for_agent(sender.workspace_id, orchestration.id, sender)
        self._delegation_for_agent(recipient.workspace_id, orchestration.id, recipient)

    @staticmethod
    def _validate_definition_pair(
        sender: AgentDefinitionVersion,
        recipient: AgentDefinitionVersion,
        policy: CommunicationPolicy,
    ) -> None:
        if (
            not sender.communication_enabled
            or not recipient.communication_enabled
            or recipient.role not in sender.allowed_recipient_roles
            or policy.allowed_recipient_roles
            and recipient.role not in policy.allowed_recipient_roles
        ):
            raise InvariantViolation("unauthorized_recipient")

    @staticmethod
    def _validate_payload(
        kind: MessageKind,
        payload: MessagePayload,
        references: tuple[CommunicationReference, ...],
        policy: CommunicationPolicy,
        schema_version: int,
    ) -> None:
        if schema_version != 1:
            raise InvariantViolation("unsupported_message_schema")
        if kind not in policy.allowed_kinds:
            raise InvariantViolation("message_kind_denied")
        if (
            payload_chars(payload) > policy.max_message_chars
            or payload_item_count(payload) > policy.max_payload_items
            or len(references) > policy.max_references
            or any(ref.kind not in policy.allowed_reference_kinds for ref in references)
        ):
            raise InvariantViolation("message_limit_exceeded")
        if isinstance(payload, RequestPayload) and payload.substantial_work:
            raise InvariantViolation("message_requires_orchestration_handoff")

    def _validate_correlation(
        self,
        workspace_id: WorkspaceId,
        thread: MessageThread,
        sender: AgentRun,
        recipient: AgentRun,
        kind: MessageKind,
        correlation_id: str,
        in_reply_to: AgentMessageId | None,
    ) -> None:
        if kind is MessageKind.RESPONSE:
            if in_reply_to is None:
                raise InvariantViolation("response_requires_request")
            request = self.store.message(workspace_id, in_reply_to)
            requester = self.store.orchestration.runtime.get_run(
                workspace_id, request.sender_agent_run_id
            )
            if (
                request.kind is not MessageKind.REQUEST
                or request.thread_id != thread.id
                or request.correlation_id != correlation_id
                or request.sender_agent_run_id != recipient.id
                or request.recipient_agent_run_id != sender.id
                or requester.status not in {AgentRunStatus.RUNNING, AgentRunStatus.WAITING}
            ):
                raise InvariantViolation("stale_or_invalid_response")
        elif in_reply_to is not None:
            raise InvariantViolation("in_reply_to_requires_response")

    def _validate_budgets(
        self,
        workspace_id: WorkspaceId,
        orchestration_run_id: OrchestrationRunId,
        thread_id: MessageThreadId,
        sender: AgentRun,
        kind: MessageKind,
        policy: CommunicationPolicy,
    ) -> None:
        run_messages = self.store.messages_for_run(workspace_id, orchestration_run_id)
        thread_messages = self.store.messages_for_thread(workspace_id, thread_id)
        agent_messages = self.store.messages_for_agent(workspace_id, sender.id)
        requests = tuple(
            item
            for item in run_messages
            if item.sender_task_id == sender.task_id and item.kind is MessageKind.REQUEST
        )
        if (
            len(run_messages) >= policy.max_messages_per_run
            or len(thread_messages) >= policy.max_messages_per_thread
            or len(agent_messages) >= policy.max_messages_per_agent_run
            or kind is MessageKind.REQUEST
            and len(requests) >= policy.max_requests_per_task
        ):
            raise InvariantViolation("communication_budget_exceeded")

    def _authorize_sender_references(
        self,
        workspace_id: WorkspaceId,
        orchestration_run_id: OrchestrationRunId,
        sender: AgentRun,
        references: tuple[CommunicationReference, ...],
    ) -> None:
        self._authorize_references(
            workspace_id,
            orchestration_run_id,
            sender,
            sender.definition_version,
            references,
        )

    def _authorize_references(
        self,
        workspace_id: WorkspaceId,
        orchestration_run_id: OrchestrationRunId,
        sender: AgentRun,
        recipient_definition: AgentDefinitionVersion,
        references: tuple[CommunicationReference, ...],
    ) -> None:
        for reference in references:
            if reference.workspace_id != workspace_id:
                raise InvariantViolation("reference_scope_mismatch")
            if reference.kind is ReferenceKind.TASK_RESULT:
                if not self._task_result_exists(
                    workspace_id, orchestration_run_id, reference.reference_id
                ):
                    raise InvariantViolation("invalid_task_result_reference")
            elif reference.kind is ReferenceKind.TOOL_RECEIPT:
                if reference.source_agent_run_id != sender.id:
                    raise InvariantViolation("reference_sender_mismatch")
                receipt = next(
                    (
                        item
                        for item in self.store.orchestration.runtime.tool_receipts(
                            workspace_id, sender.id
                        )
                        if str(item.id) == reference.reference_id
                    ),
                    None,
                )
                if receipt is None or not any(
                    grant.tool_id == receipt.invocation.tool_version.definition.id
                    and grant.version == receipt.invocation.tool_version.version
                    for grant in recipient_definition.allowed_tools
                ):
                    raise InvariantViolation("tool_reference_not_authorized")
            elif reference.kind is ReferenceKind.EVIDENCE_PACK:
                if self.knowledge is None or reference.source_agent_run_id != sender.id:
                    raise InvariantViolation("knowledge_reference_not_authorized")
                pack = self.knowledge.pack(
                    workspace_id, sender.id, EvidencePackId(reference.reference_id)
                )
                if any(
                    candidate.chunk.source_id not in recipient_definition.knowledge_scope.source_ids
                    or candidate.trust not in recipient_definition.knowledge_scope.trust_classes
                    for candidate in pack.result.candidates
                ):
                    raise InvariantViolation("knowledge_reference_not_authorized")
            elif reference.kind is ReferenceKind.MEMORY_CONTEXT_PACK:
                if self.memory is None or reference.source_agent_run_id != sender.id:
                    raise InvariantViolation("memory_reference_not_authorized")
                memory_pack = self.memory.pack(
                    workspace_id, sender.id, MemoryContextPackId(reference.reference_id)
                )
                if any(
                    hit.entry.status is not MemoryEntryStatus.ACTIVE
                    or hit.entry.scope not in recipient_definition.memory_access.scopes
                    or hit.entry.sensitivity not in recipient_definition.memory_access.sensitivities
                    for hit in memory_pack.result.hits
                ):
                    raise InvariantViolation("memory_reference_not_authorized")

    def _task_result_exists(
        self,
        workspace_id: WorkspaceId,
        orchestration_run_id: OrchestrationRunId,
        reference_id: str,
    ) -> bool:
        for delegation in self.store.orchestration.delegations(workspace_id, orchestration_run_id):
            for attempt in self.store.orchestration.attempts(workspace_id, delegation.id):
                run = self.store.orchestration.runtime.get_run(workspace_id, attempt.agent_run_id)
                if run.status is AgentRunStatus.SUCCEEDED and run.result is not None:
                    candidate = TaskResultReference(
                        run.task_id,
                        attempt.task_attempt_id,
                        run.id,
                        run.version,
                        run.result.source_references,
                    )
                    if candidate.reference == reference_id:
                        return True
        return False

    def _delegation_for_agent(
        self,
        workspace_id: WorkspaceId,
        orchestration_run_id: OrchestrationRunId,
        run: AgentRun,
    ) -> Delegation:
        for delegation in self.store.orchestration.delegations(workspace_id, orchestration_run_id):
            if any(
                attempt.agent_run_id == run.id
                for attempt in self.store.orchestration.attempts(workspace_id, delegation.id)
            ):
                return delegation
        raise InvariantViolation("agent_run_not_delegated_in_orchestration")

    def _handoff_lineage_definitions(
        self, workspace_id: WorkspaceId, handoff: HandoffRequest
    ) -> tuple[AgentDefinitionVersion, ...]:
        definitions: list[AgentDefinitionVersion] = []
        current: HandoffRequest | None = handoff
        while current is not None:
            definitions.append(
                self.store.orchestration.runtime.definition(
                    workspace_id,
                    current.sender_definition_id,
                    current.sender_definition_version,
                )
            )
            if current.recipient_definition_id is not None:
                assert current.recipient_definition_version is not None
                definitions.append(
                    self.store.orchestration.runtime.definition(
                        workspace_id,
                        current.recipient_definition_id,
                        current.recipient_definition_version,
                    )
                )
            current = (
                self.store.handoff(workspace_id, current.parent_handoff_id)
                if current.parent_handoff_id is not None
                else None
            )
        unique = {(item.definition.id, item.version): item for item in definitions}
        return tuple(unique.values())

    def _message_event(self, message: AgentMessage, kind: EventType) -> None:
        event = Event(
            self.ids.event_id(),
            message.workspace_id,
            kind,
            SubjectType.AGENT_MESSAGE,
            str(message.id),
            message.version,
            self.clock.now(),
            (
                ("kind", message.kind.value),
                ("thread_id", str(message.thread_id)),
                ("correlation_id", message.correlation_id),
            ),
        )
        self.store.append_event(event)

    def _handoff_event(self, handoff: HandoffRequest, kind: EventType) -> None:
        event = Event(
            self.ids.event_id(),
            handoff.workspace_id,
            kind,
            SubjectType.HANDOFF,
            str(handoff.id),
            handoff.version,
            self.clock.now(),
            (
                ("task_id", str(handoff.source_task_id)),
                ("depth", str(handoff.depth)),
            ),
        )
        self.store.append_event(event)
