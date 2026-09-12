"""Bounded immutable organization structure. No permission inheritance."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from agent_company_os.domain.agent import AgentDefinitionId
from agent_company_os.domain.errors import InvariantViolation, WorkspaceMismatch
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.organization_ids import (
    CapabilityId,
    DepartmentId,
    OrganizationGraphId,
    OrgRoleId,
)
from agent_company_os.domain.validation import clean_required_text, require_utc


class StructuralStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class RouteKind(StrEnum):
    DELEGATE = "delegate"
    MESSAGE = "message"
    HANDOFF = "handoff"


def label(value: str) -> None:
    clean_required_text(value, "organization_label")
    if len(value) > 200:
        raise InvariantViolation("organization_label_bound")


@dataclass(frozen=True)
class Department:
    id: DepartmentId
    workspace_id: WorkspaceId
    name: str
    status: StructuralStatus = StructuralStatus.ACTIVE
    description: str = ""

    def __post_init__(self) -> None:
        label(self.name)
        if not isinstance(self.id, DepartmentId) or not isinstance(self.status, StructuralStatus):
            raise InvariantViolation("department_schema")
        if not isinstance(self.description, str) or len(self.description) > 1000:
            raise InvariantViolation("department_description_bound")


@dataclass(frozen=True)
class OrgRole:
    id: OrgRoleId
    workspace_id: WorkspaceId
    name: str
    is_lead: bool = False

    def __post_init__(self) -> None:
        label(self.name)
        if not isinstance(self.id, OrgRoleId) or type(self.is_lead) is not bool:
            raise InvariantViolation("org_role_schema")


@dataclass(frozen=True)
class CapabilityDefinition:
    id: CapabilityId
    workspace_id: WorkspaceId
    name: str
    status: StructuralStatus = StructuralStatus.ACTIVE

    def __post_init__(self) -> None:
        label(self.name)
        if not isinstance(self.id, CapabilityId) or not isinstance(self.status, StructuralStatus):
            raise InvariantViolation("capability_schema")


@dataclass(frozen=True)
class DepartmentMembership:
    workspace_id: WorkspaceId
    agent_id: AgentDefinitionId
    department_id: DepartmentId
    role_id: OrgRoleId
    status: MembershipStatus = MembershipStatus.ACTIVE
    discoverable: bool = True
    effective_from: datetime | None = None
    effective_until: datetime | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.agent_id, AgentDefinitionId)
            or not isinstance(self.department_id, DepartmentId)
            or not isinstance(self.role_id, OrgRoleId)
            or not isinstance(self.status, MembershipStatus)
            or type(self.discoverable) is not bool
        ):
            raise InvariantViolation("membership_schema")
        for at in (self.effective_from, self.effective_until):
            if at is not None:
                require_utc(at, "membership_time")
        if (
            self.effective_from
            and self.effective_until
            and self.effective_from >= self.effective_until
        ):
            raise InvariantViolation("membership_time_order")

    def effective(self, at: datetime) -> bool:
        require_utc(at, "discovery_time")
        return (
            self.status is MembershipStatus.ACTIVE
            and (self.effective_from is None or self.effective_from <= at)
            and (self.effective_until is None or at < self.effective_until)
        )


@dataclass(frozen=True)
class ReportingRelationship:
    workspace_id: WorkspaceId
    subordinate: AgentDefinitionId
    manager: AgentDefinitionId

    def __post_init__(self) -> None:
        if not isinstance(self.subordinate, AgentDefinitionId) or not isinstance(
            self.manager, AgentDefinitionId
        ):
            raise InvariantViolation("reporting_identity_schema")


@dataclass(frozen=True)
class RegisteredAgent:
    """Exact reference only; RuntimeStore remains configuration authority."""

    workspace_id: WorkspaceId
    agent_id: AgentDefinitionId
    version: Version

    def __post_init__(self) -> None:
        if not isinstance(self.agent_id, AgentDefinitionId) or not isinstance(
            self.version, Version
        ):
            raise InvariantViolation("registered_agent_schema")


@dataclass(frozen=True)
class DepartmentRoute:
    source: DepartmentId
    target: DepartmentId
    kind: RouteKind
    allowed: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source, DepartmentId)
            or not isinstance(self.target, DepartmentId)
            or not isinstance(self.kind, RouteKind)
            or type(self.allowed) is not bool
        ):
            raise InvariantViolation("organization_route_schema")


@dataclass(frozen=True)
class OrganizationBounds:
    departments: int = 12
    roles: int = 16
    capabilities: int = 32
    memberships: int = 64
    memberships_per_agent: int = 3
    agents_per_department: int = 20
    reporting_depth: int = 5
    cross_department_rules: int = 64

    def __post_init__(self) -> None:
        for value, maximum in (
            (self.departments, 32),
            (self.roles, 64),
            (self.capabilities, 128),
            (self.memberships, 256),
            (self.memberships_per_agent, 8),
            (self.agents_per_department, 64),
            (self.reporting_depth, 10),
            (self.cross_department_rules, 256),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise InvariantViolation("organization_bounds")


@dataclass(frozen=True)
class OrganizationPolicy:
    routes: tuple[DepartmentRoute, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.routes, tuple)
            or len(self.routes) > 256
            or any(not isinstance(r, DepartmentRoute) for r in self.routes)
        ):
            raise InvariantViolation("organization_policy_schema")

    def allows(self, source: DepartmentId, target: DepartmentId, kind: RouteKind) -> bool:
        for rule in self.routes:
            if (rule.source, rule.target, rule.kind) == (source, target, kind):
                return rule.allowed
        return source == target


@dataclass(frozen=True)
class OrganizationGraph:
    id: OrganizationGraphId
    workspace_id: WorkspaceId
    name: str
    revision: Version = Version(1)
    active_version: Version | None = None

    def __post_init__(self) -> None:
        label(self.name)
        if not isinstance(self.id, OrganizationGraphId) or not isinstance(
            self.workspace_id, WorkspaceId
        ):
            raise InvariantViolation("organization_graph_identity_schema")


@dataclass(frozen=True)
class OrganizationGraphVersion:
    graph_id: OrganizationGraphId
    workspace_id: WorkspaceId
    version: Version
    created_at: datetime
    departments: tuple[Department, ...]
    roles: tuple[OrgRole, ...]
    capabilities: tuple[CapabilityDefinition, ...]
    agents: tuple[RegisteredAgent, ...]
    memberships: tuple[DepartmentMembership, ...]
    reporting: tuple[ReportingRelationship, ...] = ()
    policy: OrganizationPolicy = OrganizationPolicy()
    bounds: OrganizationBounds = OrganizationBounds()
    schema_version: int = 1

    def __post_init__(self) -> None:
        require_utc(self.created_at, "organization_created_at")
        collections = (
            self.departments,
            self.roles,
            self.capabilities,
            self.agents,
            self.memberships,
            self.reporting,
            self.policy.routes,
        )
        maxima = (
            self.bounds.departments,
            self.bounds.roles,
            self.bounds.capabilities,
            self.bounds.memberships,
            self.bounds.memberships,
            self.bounds.memberships,
            self.bounds.cross_department_rules,
        )
        if self.schema_version != 1 or any(
            not isinstance(items, tuple) or len(items) > maximum
            for items, maximum in zip(collections, maxima, strict=True)
        ):
            raise InvariantViolation("organization_graph_bound_or_schema")
        for items in collections[:-1]:
            for item in items:
                if item.workspace_id != self.workspace_id:
                    raise WorkspaceMismatch(
                        "OrganizationGraph", str(self.workspace_id), str(item.workspace_id)
                    )
        departments = {d.id: d for d in self.departments}
        roles = {r.id: r for r in self.roles}
        capabilities = {c.id: c for c in self.capabilities}
        agents = {a.agent_id: a for a in self.agents}
        if any(
            len(mapping) != len(items)
            for mapping, items in (
                (departments, self.departments),
                (roles, self.roles),
                (capabilities, self.capabilities),
                (agents, self.agents),
            )
        ):
            raise InvariantViolation("organization_unique_ids")
        keys = [(m.agent_id, m.department_id, m.role_id) for m in self.memberships]
        if len(keys) != len(set(keys)):
            raise InvariantViolation("duplicate_membership")
        for member in self.memberships:
            if (
                member.department_id not in departments
                or member.role_id not in roles
                or member.agent_id not in agents
            ):
                raise InvariantViolation("unknown_membership_reference")
        for agent in agents:
            if (
                sum(m.agent_id == agent for m in self.memberships)
                > self.bounds.memberships_per_agent
            ):
                raise InvariantViolation("memberships_per_agent_bound")
        for department in departments:
            members = tuple(m for m in self.memberships if m.department_id == department)
            if len({m.agent_id for m in members}) > self.bounds.agents_per_department:
                raise InvariantViolation("agents_per_department_bound")
            # At most one active lead, even if future effective windows do not overlap.
            if (
                sum(
                    m.status is MembershipStatus.ACTIVE and roles[m.role_id].is_lead
                    for m in members
                )
                > 1
            ):
                raise InvariantViolation("department_lead_unique")
        parents: dict[AgentDefinitionId, AgentDefinitionId] = {}
        for edge in self.reporting:
            if (
                edge.subordinate not in agents
                or edge.manager not in agents
                or edge.subordinate == edge.manager
            ):
                raise InvariantViolation("invalid_reporting_edge")
            if edge.subordinate in parents:
                raise InvariantViolation("one_reporting_manager")
            parents[edge.subordinate] = edge.manager
        for start in parents:
            seen: set[AgentDefinitionId] = set()
            node = start
            while node in parents:
                if node in seen:
                    raise InvariantViolation("reporting_cycle")
                seen.add(node)
                if len(seen) > self.bounds.reporting_depth:
                    raise InvariantViolation("reporting_depth_bound")
                node = parents[node]
        route_keys = [(r.source, r.target, r.kind) for r in self.policy.routes]
        if len(route_keys) != len(set(route_keys)) or any(
            r.source not in departments or r.target not in departments for r in self.policy.routes
        ):
            raise InvariantViolation("invalid_department_route")


@dataclass(frozen=True)
class OrganizationSnapshot:
    graph: OrganizationGraphVersion
    captured_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.captured_at, "organization_capture_time")


@dataclass(frozen=True)
class RegistryQuery:
    department_id: DepartmentId | None = None
    role_id: OrgRoleId | None = None
    capability_ids: tuple[CapabilityId, ...] = ()

    def __post_init__(self) -> None:
        if (
            self.department_id is not None
            and not isinstance(self.department_id, DepartmentId)
            or self.role_id is not None
            and not isinstance(self.role_id, OrgRoleId)
        ):
            raise InvariantViolation("registry_query_identity")
        if (
            not isinstance(self.capability_ids, tuple)
            or len(self.capability_ids) > 10
            or any(not isinstance(c, CapabilityId) for c in self.capability_ids)
            or len(set(self.capability_ids)) != len(self.capability_ids)
        ):
            raise InvariantViolation("registry_query_schema")
