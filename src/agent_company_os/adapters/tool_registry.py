"""Deterministic registry of exact immutable published versions."""

from threading import RLock

from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.ids import WorkspaceId
from agent_company_os.domain.tools import ToolError, ToolFailure, ToolGrant, ToolId, ToolVersion
from agent_company_os.ports.tools import ResolvedTool, ToolExecutor


class ToolRegistry:
    def known(self, workspace_id: WorkspaceId, tool_id: ToolId) -> bool:
        with self._lock:
            return any(
                entry.version.definition.workspace_id == workspace_id and grant.tool_id == tool_id
                for grant, entry in self._entries.items()
            )

    def __init__(self) -> None:
        self._entries: dict[ToolGrant, ResolvedTool] = {}
        self._enabled: dict[ToolId, bool] = {}
        self._revisions: dict[ToolId, int] = {}
        self._lock = RLock()

    def publish(self, version: ToolVersion, executor: ToolExecutor) -> None:
        with self._lock:
            if version.grant in self._entries:
                raise InvariantViolation("published_tool_version_immutable")
            lineage = [
                entry.version
                for entry in self._entries.values()
                if entry.version.definition.id == version.definition.id
            ]
            if lineage and lineage[0].definition != version.definition:
                raise InvariantViolation("tool_lineage_identity_immutable")
            if version.version.value != len(lineage) + 1:
                raise InvariantViolation("tool_version_sequence")
            self._entries[version.grant] = ResolvedTool(version, executor, 0)
            self._enabled.setdefault(version.definition.id, True)
            self._revisions.setdefault(version.definition.id, 0)

    def set_enabled(self, workspace_id: WorkspaceId, tool_id: ToolId, enabled: bool) -> None:
        with self._lock:
            candidates = [
                entry for grant, entry in self._entries.items() if grant.tool_id == tool_id
            ]
            if not candidates:
                raise ToolFailure(ToolError.NOT_FOUND)
            if candidates[0].version.definition.workspace_id != workspace_id:
                raise ToolFailure(ToolError.UNAUTHORIZED)
            self._enabled[tool_id] = enabled
            self._revisions[tool_id] += 1

    def resolve(self, workspace_id: WorkspaceId, grant: ToolGrant) -> ResolvedTool:
        with self._lock:
            entry = self._entries.get(grant)
            if entry is None:
                raise ToolFailure(ToolError.NOT_FOUND)
            if (
                entry.version.definition.workspace_id != workspace_id
                or not self._enabled[grant.tool_id]
            ):
                raise ToolFailure(ToolError.UNAUTHORIZED)
            return ResolvedTool(entry.version, entry.executor, self._revisions[grant.tool_id])
