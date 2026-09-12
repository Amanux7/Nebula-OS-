"""Atomic in-process communication history over the orchestration boundary."""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager

from agent_company_os.domain.agent import AgentRunId
from agent_company_os.domain.communication import (
    AgentMessage,
    AgentMessageId,
    HandoffId,
    HandoffRequest,
    MessageThread,
    MessageThreadId,
)
from agent_company_os.domain.errors import (
    EntityNotFound,
    InvariantViolation,
    VersionConflict,
    WorkspaceMismatch,
)
from agent_company_os.domain.events import Event
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.orchestration import OrchestrationRunId
from agent_company_os.domain.transitions import SubjectType
from agent_company_os.ports.orchestration import OrchestrationStore


class InMemoryCommunicationStore:
    def __init__(self, orchestration: OrchestrationStore) -> None:
        self.orchestration = orchestration
        self._threads: dict[MessageThreadId, MessageThread] = {}
        self._messages: dict[AgentMessageId, AgentMessage] = {}
        self._handoffs: dict[HandoffId, HandoffRequest] = {}
        self._events: list[Event] = []

    @contextmanager
    def atomic(self) -> Iterator[None]:
        with self.orchestration.atomic():
            snapshot = (
                self._threads.copy(),
                self._messages.copy(),
                self._handoffs.copy(),
                self._events.copy(),
            )
            try:
                yield
            except BaseException:
                self._threads, self._messages, self._handoffs, self._events = snapshot
                raise

    @staticmethod
    def _scope(expected: WorkspaceId, actual: WorkspaceId, name: str) -> None:
        if expected != actual:
            raise WorkspaceMismatch(name, str(expected), str(actual))

    def add_thread(self, thread: MessageThread) -> None:
        with self.atomic():
            run = self.orchestration.run(thread.workspace_id, thread.orchestration_run_id)
            creator = self.orchestration.runtime.get_run(thread.workspace_id, thread.created_by)
            if (
                thread.id in self._threads
                or thread.version != Version(1)
                or creator.goal_id != run.goal_id
            ):
                raise InvariantViolation("message_thread_binding")
            self._threads[thread.id] = thread

    def thread(self, workspace_id: WorkspaceId, thread_id: MessageThreadId) -> MessageThread:
        try:
            thread = self._threads[thread_id]
        except KeyError as error:
            raise EntityNotFound("MessageThread", str(thread_id)) from error
        self._scope(workspace_id, thread.workspace_id, "MessageThread")
        return thread

    def add_message(self, message: AgentMessage) -> None:
        with self.atomic():
            thread = self.thread(message.workspace_id, message.thread_id)
            run = self.orchestration.run(message.workspace_id, message.orchestration_run_id)
            sender = self.orchestration.runtime.get_run(
                message.workspace_id, message.sender_agent_run_id
            )
            recipient = self.orchestration.runtime.get_run(
                message.workspace_id, message.recipient_agent_run_id
            )
            if (
                message.id in self._messages
                or message.version != Version(1)
                or thread.orchestration_run_id != run.id
                or sender.definition_version.definition.id != message.sender_definition_id
                or sender.definition_version.version != message.sender_definition_version
                or recipient.definition_version.definition.id != message.recipient_definition_id
                or recipient.definition_version.version != message.recipient_definition_version
                or sender.task_id != message.sender_task_id
                or recipient.task_id != message.recipient_task_id
            ):
                raise InvariantViolation("agent_message_binding")
            self._messages[message.id] = message

    def message(self, workspace_id: WorkspaceId, message_id: AgentMessageId) -> AgentMessage:
        try:
            message = self._messages[message_id]
        except KeyError as error:
            raise EntityNotFound("AgentMessage", str(message_id)) from error
        self._scope(workspace_id, message.workspace_id, "AgentMessage")
        return message

    def save_message(self, message: AgentMessage, expected: Version) -> None:
        with self.atomic():
            previous = self.message(message.workspace_id, message.id)
            if previous.version != expected:
                raise VersionConflict(
                    "AgentMessage", str(message.id), expected.value, previous.version.value
                )
            if message.version != expected.next():
                raise InvariantViolation("message_version_increment")
            self._messages[message.id] = message

    def messages_for_thread(
        self, workspace_id: WorkspaceId, thread_id: MessageThreadId
    ) -> tuple[AgentMessage, ...]:
        self.thread(workspace_id, thread_id)
        return self._ordered(
            message for message in self._messages.values() if message.thread_id == thread_id
        )

    def messages_for_run(
        self, workspace_id: WorkspaceId, run_id: OrchestrationRunId
    ) -> tuple[AgentMessage, ...]:
        self.orchestration.run(workspace_id, run_id)
        return self._ordered(
            message for message in self._messages.values() if message.orchestration_run_id == run_id
        )

    def messages_for_agent(
        self, workspace_id: WorkspaceId, agent_run_id: AgentRunId
    ) -> tuple[AgentMessage, ...]:
        self.orchestration.runtime.get_run(workspace_id, agent_run_id)
        return self._ordered(
            message
            for message in self._messages.values()
            if agent_run_id in {message.sender_agent_run_id, message.recipient_agent_run_id}
        )

    @staticmethod
    def _ordered(messages: Iterable[AgentMessage]) -> tuple[AgentMessage, ...]:
        return tuple(sorted(messages, key=lambda item: (item.created_at, str(item.id))))

    def add_handoff(self, handoff: HandoffRequest) -> None:
        with self.atomic():
            run = self.orchestration.run(handoff.workspace_id, handoff.orchestration_run_id)
            sender = self.orchestration.runtime.get_run(
                handoff.workspace_id, handoff.sender_agent_run_id
            )
            delegation = self.orchestration.delegation(
                handoff.workspace_id, handoff.source_delegation_id
            )
            if (
                handoff.id in self._handoffs
                or handoff.version != Version(1)
                or sender.goal_id != run.goal_id
                or sender.task_id != handoff.source_task_id
                or delegation.task_id != handoff.source_task_id
                or delegation.orchestration_run_id != run.id
            ):
                raise InvariantViolation("handoff_binding")
            self._handoffs[handoff.id] = handoff

    def handoff(self, workspace_id: WorkspaceId, handoff_id: HandoffId) -> HandoffRequest:
        try:
            handoff = self._handoffs[handoff_id]
        except KeyError as error:
            raise EntityNotFound("HandoffRequest", str(handoff_id)) from error
        self._scope(workspace_id, handoff.workspace_id, "HandoffRequest")
        return handoff

    def save_handoff(self, handoff: HandoffRequest, expected: Version) -> None:
        with self.atomic():
            previous = self.handoff(handoff.workspace_id, handoff.id)
            if previous.version != expected:
                raise VersionConflict(
                    "HandoffRequest", str(handoff.id), expected.value, previous.version.value
                )
            if handoff.version != expected.next():
                raise InvariantViolation("handoff_version_increment")
            if handoff.resulting_delegation_id is not None:
                delegation = self.orchestration.delegation(
                    handoff.workspace_id, handoff.resulting_delegation_id
                )
                if delegation.task_id != handoff.source_task_id:
                    raise InvariantViolation("handoff_resulting_delegation_binding")
            self._handoffs[handoff.id] = handoff

    def handoffs_for_run(
        self, workspace_id: WorkspaceId, run_id: OrchestrationRunId
    ) -> tuple[HandoffRequest, ...]:
        self.orchestration.run(workspace_id, run_id)
        return tuple(
            sorted(
                (
                    handoff
                    for handoff in self._handoffs.values()
                    if handoff.orchestration_run_id == run_id
                ),
                key=lambda item: (item.created_at, str(item.id)),
            )
        )

    def append_event(self, event: Event) -> None:
        if event.subject_type is SubjectType.AGENT_MESSAGE:
            version = self.message(event.workspace_id, AgentMessageId(event.subject_id)).version
        elif event.subject_type is SubjectType.HANDOFF:
            version = self.handoff(event.workspace_id, HandoffId(event.subject_id)).version
        elif event.subject_type is SubjectType.MESSAGE_THREAD:
            version = self.thread(event.workspace_id, MessageThreadId(event.subject_id)).version
        else:
            raise InvariantViolation("communication_event_subject")
        if version != event.entity_version or any(old.id == event.id for old in self._events):
            raise InvariantViolation("communication_event_binding")
        self._events.append(event)

    def events(self, workspace_id: WorkspaceId) -> tuple[Event, ...]:
        self.orchestration.runtime.domain.get_workspace(workspace_id)
        return tuple(event for event in self._events if event.workspace_id == workspace_id)
