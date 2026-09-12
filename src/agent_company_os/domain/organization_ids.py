"""Opaque organizational identities, independent of runtime participation."""

from agent_company_os.domain.ids import OpaqueId


class OrganizationGraphId(OpaqueId):
    pass


class DepartmentId(OpaqueId):
    pass


class OrgRoleId(OpaqueId):
    pass


class CapabilityId(OpaqueId):
    pass
