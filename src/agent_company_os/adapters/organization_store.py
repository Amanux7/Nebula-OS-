"""Atomic organization snapshots over the existing runtime lock."""

from collections.abc import Iterator
from contextlib import contextmanager

from agent_company_os.domain.errors import EntityNotFound, InvariantViolation, VersionConflict
from agent_company_os.domain.events import Event
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.organization import OrganizationGraph, OrganizationGraphVersion
from agent_company_os.ports.runtime_store import RuntimeStore


class InMemoryOrganizationStore:
    def __init__(self, runtime: RuntimeStore) -> None:
        self.runtime = runtime
        self._graphs: dict[WorkspaceId, OrganizationGraph] = {}
        self._versions: dict[tuple[WorkspaceId, Version], OrganizationGraphVersion] = {}
        self._events: list[Event] = []

    @contextmanager
    def atomic(self) -> Iterator[None]:
        with self.runtime.atomic():
            before = self._graphs.copy(), self._versions.copy(), self._events.copy()
            try:
                yield
            except BaseException:
                self._graphs, self._versions, self._events = before
                raise

    def graph(self, workspace_id: WorkspaceId) -> OrganizationGraph:
        self.runtime.domain.get_workspace(workspace_id)
        try:
            return self._graphs[workspace_id]
        except KeyError as error:
            raise EntityNotFound("OrganizationGraph", str(workspace_id)) from error

    def add_graph(self, graph: OrganizationGraph) -> None:
        with self.atomic():
            self.runtime.domain.get_workspace(graph.workspace_id)
            if (
                graph.workspace_id in self._graphs
                or graph.revision != Version(1)
                or graph.active_version is not None
                or any(g.id == graph.id for g in self._graphs.values())
            ):
                raise InvariantViolation("organization_graph_identity")
            self._graphs[graph.workspace_id] = graph

    def save_graph(self, graph: OrganizationGraph, expected: Version) -> None:
        previous = self.graph(graph.workspace_id)
        if previous.revision != expected:
            raise VersionConflict(
                "OrganizationGraph", str(graph.id), expected.value, previous.revision.value
            )
        if (
            graph.id != previous.id
            or graph.name != previous.name
            or graph.revision != expected.next()
        ):
            raise InvariantViolation("organization_graph_mutation")
        if graph.active_version is not None:
            self.version(graph.workspace_id, graph.active_version)
        self._graphs[graph.workspace_id] = graph

    def add_version(self, version: OrganizationGraphVersion) -> None:
        graph = self.graph(version.workspace_id)
        if (
            graph.id != version.graph_id
            or version.version.value != len(self.versions(version.workspace_id)) + 1
        ):
            raise InvariantViolation("organization_version_lineage")
        for agent in version.agents:
            self.runtime.definition(version.workspace_id, agent.agent_id, agent.version)
        self._versions[(version.workspace_id, version.version)] = version

    def version(self, workspace_id: WorkspaceId, version: Version) -> OrganizationGraphVersion:
        self.graph(workspace_id)
        try:
            return self._versions[(workspace_id, version)]
        except KeyError as error:
            raise EntityNotFound("OrganizationGraphVersion", str(version.value)) from error

    def versions(self, workspace_id: WorkspaceId) -> tuple[OrganizationGraphVersion, ...]:
        self.graph(workspace_id)
        return tuple(
            v
            for (w, _), v in sorted(self._versions.items(), key=lambda pair: pair[0][1].value)
            if w == workspace_id
        )

    def append_event(self, event: Event) -> None:
        graph = self.graph(event.workspace_id)
        if event.subject_id != str(graph.id) or any(e.id == event.id for e in self._events):
            raise InvariantViolation("organization_event_binding")
        self._events.append(event)

    def events(self, workspace_id: WorkspaceId) -> tuple[Event, ...]:
        self.graph(workspace_id)
        return tuple(e for e in self._events if e.workspace_id == workspace_id)
