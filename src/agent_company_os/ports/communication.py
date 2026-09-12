"""Storage and runtime seams for bounded in-process agent communication."""

from contextlib import AbstractContextManager
from typing import Protocol

from agent_company_os.domain.agent import AgentRun, AgentRunId
from agent_company_os.domain.communication import (
    AgentMessage,
    AgentMessageContext,
    AgentMessageId,
    HandoffId,
    HandoffRequest,
    MessageThread,
    MessageThreadId,
)
from agent_company_os.domain.events import Event
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.orchestration import OrchestrationRunId
from agent_company_os.ports.orchestration import OrchestrationStore


class CommunicationStore(Protocol):
    orchestration: OrchestrationStore

    def atomic(self) -> AbstractContextManager[None]: ...
    def add_thread(self, thread: MessageThread) -> None: ...
    def thread(self, workspace_id: WorkspaceId, thread_id: MessageThreadId) -> MessageThread: ...
    def add_message(self, message: AgentMessage) -> None: ...
    def message(self, workspace_id: WorkspaceId, message_id: AgentMessageId) -> AgentMessage: ...
    def save_message(self, message: AgentMessage, expected: Version) -> None: ...
    def messages_for_thread(
        self, workspace_id: WorkspaceId, thread_id: MessageThreadId
    ) -> tuple[AgentMessage, ...]: ...
    def messages_for_run(
        self, workspace_id: WorkspaceId, run_id: OrchestrationRunId
    ) -> tuple[AgentMessage, ...]: ...
    def messages_for_agent(
        self, workspace_id: WorkspaceId, agent_run_id: AgentRunId
    ) -> tuple[AgentMessage, ...]: ...
    def add_handoff(self, handoff: HandoffRequest) -> None: ...
    def handoff(self, workspace_id: WorkspaceId, handoff_id: HandoffId) -> HandoffRequest: ...
    def save_handoff(self, handoff: HandoffRequest, expected: Version) -> None: ...
    def handoffs_for_run(
        self, workspace_id: WorkspaceId, run_id: OrchestrationRunId
    ) -> tuple[HandoffRequest, ...]: ...
    def append_event(self, event: Event) -> None: ...


class CommunicationRuntimePort(Protocol):
    def context_for(self, run: AgentRun) -> AgentMessageContext | None: ...
