"""Test-only subprocess: die after independent remote commit, without finally/close."""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from agent_company_os.adapters.clocks import FakeClock
from agent_company_os.adapters.fake_model import FakeModel
from agent_company_os.adapters.ids import DeterministicIdGenerator
from agent_company_os.adapters.recoverable_fixture import RecoverableFixtureExecutor
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.application.governance import GovernanceService
from agent_company_os.application.runtime import AgentRuntimeService
from agent_company_os.application.tool_runtime import ToolRuntimeService
from agent_company_os.domain.agent import AgentRunId
from agent_company_os.domain.governance import ActionIntentId
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.tools import ToolInput, ToolInvocation


class CrashExecutor(RecoverableFixtureExecutor):
    async def execute(self, request: ToolInput, invocation: ToolInvocation) -> str:
        await super().execute(request, invocation)
        os._exit(73)


if __name__ == "__main__":
    path, remote, timestamp, workspace, run_id, intent_id, version = sys.argv[1:]
    clock = FakeClock(datetime.fromisoformat(timestamp))
    graph = SqliteStoreGroup(Path(path))
    executor = CrashExecutor(Path(remote))
    ws, run = WorkspaceId(workspace), AgentRunId(run_id)
    definition = graph.runtime.get_run(ws, run).definition_version
    graph.registry.bind(definition.allowed_tools[0], executor)
    ids = DeterministicIdGenerator("crashed-worker")
    governance = GovernanceService(graph.runtime, clock, ids)
    tools = ToolRuntimeService(graph.runtime, graph.registry, clock, ids, governance)
    runtime = AgentRuntimeService(graph.runtime, clock, ids, FakeModel(()), tools)
    asyncio.run(runtime.resume_approval(ws, run, ActionIntentId(intent_id), Version(int(version))))
