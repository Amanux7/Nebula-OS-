"""Organization publication and read-only runtime discovery seams."""

from contextlib import AbstractContextManager
from typing import Protocol

from agent_company_os.domain.agent import AgentDefinitionVersion
from agent_company_os.domain.events import Event
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.organization import (
    OrganizationGraph,
    OrganizationGraphVersion,
    OrganizationSnapshot,
    RegistryQuery,
    RouteKind,
)
from agent_company_os.domain.organization_ids import DepartmentId
from agent_company_os.ports.runtime_store import RuntimeStore


class OrganizationStore(Protocol):
    runtime: RuntimeStore

    def atomic(self) -> AbstractContextManager[None]: ...
    def graph(self, workspace_id: WorkspaceId) -> OrganizationGraph: ...
    def add_graph(self, graph: OrganizationGraph) -> None: ...
    def save_graph(self, graph: OrganizationGraph, expected: Version) -> None: ...
    def add_version(self, version: OrganizationGraphVersion) -> None: ...
    def version(self, workspace_id: WorkspaceId, version: Version) -> OrganizationGraphVersion: ...
    def versions(self, workspace_id: WorkspaceId) -> tuple[OrganizationGraphVersion, ...]: ...
    def append_event(self, event: Event) -> None: ...


class AgentRegistryPort(Protocol):
    def capture(self, workspace_id: WorkspaceId) -> OrganizationSnapshot: ...
    def query(
        self,
        workspace_id: WorkspaceId,
        snapshot: OrganizationSnapshot,
        query: RegistryQuery | None = None,
    ) -> tuple[AgentDefinitionVersion, ...]: ...
    def require_route(
        self,
        workspace_id: WorkspaceId,
        snapshot: OrganizationSnapshot,
        source: AgentDefinitionVersion | DepartmentId,
        target: AgentDefinitionVersion,
        kind: RouteKind,
    ) -> None: ...
