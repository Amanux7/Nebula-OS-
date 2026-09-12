"""Host-only organization publication and deterministic directory queries."""

from dataclasses import replace

from agent_company_os.domain.agent import AgentDefinitionVersion
from agent_company_os.domain.errors import InvariantViolation, VersionConflict, WorkspaceMismatch
from agent_company_os.domain.events import Event, EventType
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.organization import (
    DepartmentMembership,
    OrganizationGraph,
    OrganizationGraphVersion,
    OrganizationSnapshot,
    RegistryQuery,
    RouteKind,
    StructuralStatus,
    label,
)
from agent_company_os.domain.organization_ids import DepartmentId
from agent_company_os.domain.transitions import SubjectType
from agent_company_os.ports.clock import Clock
from agent_company_os.ports.ids import IdGenerator
from agent_company_os.ports.organization import OrganizationStore


class OrganizationService:
    def __init__(self, store: OrganizationStore, clock: Clock, ids: IdGenerator) -> None:
        self.store, self.clock, self.ids = store, clock, ids

    def create(self, workspace_id: WorkspaceId, name: str) -> OrganizationGraph:
        label(name)
        graph = OrganizationGraph(self.ids.organization_graph_id(), workspace_id, name)
        self.store.add_graph(graph)
        return graph

    def publish(
        self, draft: OrganizationGraphVersion, expected: Version
    ) -> OrganizationGraphVersion:
        with self.store.atomic():
            graph = self.store.graph(draft.workspace_id)
            if graph.revision != expected:
                raise VersionConflict(
                    "OrganizationGraph", str(graph.id), expected.value, graph.revision.value
                )
            # Reconstruct to validate even a forged dataclass supplied by a host adapter.
            draft = replace(draft)
            self._validate_definitions(draft)
            self.store.add_version(draft)
            self.store.save_graph(replace(graph, revision=graph.revision.next()), expected)
            self._event(draft, EventType.ORGANIZATION_GRAPH_VERSION_CREATED)
            return draft

    def _validate_definitions(self, draft: OrganizationGraphVersion) -> None:
        capabilities = {c.id for c in draft.capabilities}
        for ref in draft.agents:
            definition = self.store.runtime.definition(
                draft.workspace_id, ref.agent_id, ref.version
            )
            if not set(definition.capability_ids) <= capabilities:
                raise InvariantViolation("unknown_registered_capability")

    def activate(
        self, workspace_id: WorkspaceId, version: Version, expected: Version
    ) -> OrganizationGraph:
        with self.store.atomic():
            graph = self.store.graph(workspace_id)
            draft = replace(self.store.version(workspace_id, version))
            self._validate_definitions(draft)
            updated = replace(graph, active_version=version, revision=graph.revision.next())
            self.store.save_graph(updated, expected)
            self._event(draft, EventType.ORGANIZATION_GRAPH_ACTIVATED)
            return updated

    def _event(self, version: OrganizationGraphVersion, kind: EventType) -> None:
        self.store.append_event(
            Event(
                self.ids.event_id(),
                version.workspace_id,
                kind,
                SubjectType.ORGANIZATION_GRAPH,
                str(version.graph_id),
                version.version,
                self.clock.now(),
                (
                    ("department_count", str(len(version.departments))),
                    ("membership_count", str(len(version.memberships))),
                    ("capability_count", str(len(version.capabilities))),
                ),
            )
        )


class AgentRegistry:
    """Returns canonical candidate definitions; never grants or executes anything."""

    def __init__(self, store: OrganizationStore, clock: Clock) -> None:
        self.store, self.clock = store, clock

    def capture(self, workspace_id: WorkspaceId) -> OrganizationSnapshot:
        with self.store.atomic():
            graph = self.store.graph(workspace_id)
            if graph.active_version is None:
                raise InvariantViolation("organization_requires_active_version")
            return OrganizationSnapshot(
                self.store.version(workspace_id, graph.active_version), self.clock.now()
            )

    def _validate(self, workspace_id: WorkspaceId, snapshot: OrganizationSnapshot) -> None:
        if snapshot.graph.workspace_id != workspace_id:
            raise WorkspaceMismatch(
                "OrganizationSnapshot", str(workspace_id), str(snapshot.graph.workspace_id)
            )
        if self.store.version(workspace_id, snapshot.graph.version) != snapshot.graph:
            raise InvariantViolation("forged_organization_snapshot")

    def _members(self, snapshot: OrganizationSnapshot) -> tuple[DepartmentMembership, ...]:
        at = self.clock.now()
        active = {d.id for d in snapshot.graph.departments if d.status is StructuralStatus.ACTIVE}
        return tuple(
            m for m in snapshot.graph.memberships if m.department_id in active and m.effective(at)
        )

    def query(
        self,
        workspace_id: WorkspaceId,
        snapshot: OrganizationSnapshot,
        query: RegistryQuery | None = None,
    ) -> tuple[AgentDefinitionVersion, ...]:
        self._validate(workspace_id, snapshot)
        query = query or RegistryQuery()
        graph = snapshot.graph
        if (
            (
                query.department_id is not None
                and query.department_id not in {d.id for d in graph.departments}
            )
            or (query.role_id is not None and query.role_id not in {r.id for r in graph.roles})
            or not set(query.capability_ids) <= {c.id for c in graph.capabilities}
        ):
            raise InvariantViolation("unknown_registry_filter")
        active_caps = {c.id for c in graph.capabilities if c.status is StructuralStatus.ACTIVE}
        members = self._members(snapshot)
        result = []
        for ref in graph.agents:
            item = self.store.runtime.definition(workspace_id, ref.agent_id, ref.version)
            if (
                not item.enabled
                or not set(query.capability_ids) <= set(item.capability_ids) & active_caps
            ):
                continue
            if any(
                m.agent_id == ref.agent_id
                and m.discoverable
                and (query.department_id is None or query.department_id == m.department_id)
                and (query.role_id is None or query.role_id == m.role_id)
                for m in members
            ):
                result.append(item)
        return tuple(sorted(result, key=lambda a: (str(a.definition.id), a.version.value)))

    def require_route(
        self,
        workspace_id: WorkspaceId,
        snapshot: OrganizationSnapshot,
        source: AgentDefinitionVersion | DepartmentId,
        target: AgentDefinitionVersion,
        kind: RouteKind,
    ) -> None:
        self._validate(workspace_id, snapshot)
        candidates = self.query(workspace_id, snapshot)
        if (
            target not in candidates
            or isinstance(source, AgentDefinitionVersion)
            and source not in candidates
        ):
            raise InvariantViolation("organization_participant_unavailable")
        members = self._members(snapshot)
        sources = (
            {source}
            if isinstance(source, DepartmentId)
            else {m.department_id for m in members if m.agent_id == source.definition.id}
        )
        targets = {m.department_id for m in members if m.agent_id == target.definition.id}
        active = {d.id for d in snapshot.graph.departments if d.status is StructuralStatus.ACTIVE}
        if (
            not sources <= active
            or not sources
            or not targets
            or not all(snapshot.graph.policy.allows(s, t, kind) for s in sources for t in targets)
        ):
            raise InvariantViolation("organization_route_denied")

    def escalation_target(
        self, workspace_id: WorkspaceId, snapshot: OrganizationSnapshot, department_id: DepartmentId
    ) -> AgentDefinitionVersion | None:
        leads = {r.id for r in snapshot.graph.roles if r.is_lead}
        candidates = self.query(workspace_id, snapshot, RegistryQuery(department_id))
        return next(
            (
                a
                for a in candidates
                if any(
                    m.agent_id == a.definition.id
                    and m.department_id == department_id
                    and m.role_id in leads
                    for m in self._members(snapshot)
                )
            ),
            None,
        )
