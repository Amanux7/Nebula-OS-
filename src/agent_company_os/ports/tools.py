"""Tool execution and registry seams; adapters never enter model context."""

from dataclasses import dataclass
from typing import Protocol

from agent_company_os.domain.agent import AgentRun, AgentRunId, Fact
from agent_company_os.domain.decisions import Action
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.tools import ToolGrant, ToolId, ToolInput, ToolInvocation, ToolVersion


class ToolExecutor(Protocol):
    async def execute(self, request: ToolInput, context: ToolInvocation) -> str:
        """Nonblocking cooperative operation, returning untrusted bounded JSON."""
        ...


@dataclass(frozen=True)
class ResolvedTool:
    version: ToolVersion
    executor: ToolExecutor
    revision: int


class ToolRegistryPort(Protocol):
    def known(self, workspace_id: WorkspaceId, tool_id: ToolId) -> bool: ...
    def resolve(self, workspace_id: WorkspaceId, grant: ToolGrant) -> ResolvedTool: ...


class ToolRuntimePort(Protocol):
    async def invoke(
        self,
        workspace_id: WorkspaceId,
        run_id: AgentRunId,
        action: Action,
        expected_version: Version,
    ) -> AgentRun: ...
    def evidence(self, run: AgentRun) -> tuple[Fact, ...]: ...
    def descriptors(self, run: AgentRun) -> tuple[ToolVersion, ...]: ...
