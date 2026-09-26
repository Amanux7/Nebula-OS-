"""Human control-plane identity, distinct from agents and approval reviewers."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from agent_company_os.domain.errors import DomainError, InvariantViolation
from agent_company_os.domain.ids import OpaqueId, Version, WorkspaceId
from agent_company_os.domain.validation import require_utc


class OperatorId(OpaqueId):
    """Locally provisioned human/operator identity."""


class OperatorRole(StrEnum):
    VIEWER = "viewer"
    AUDITOR = "auditor"
    OPERATOR = "operator"
    ADMIN = "admin"


class OperatorResource(StrEnum):
    OPERATIONAL = "operational"
    AUDIT = "audit"
    RECOVERY = "recovery"
    SENSITIVE = "sensitive"
    ACCOUNT_ADMIN = "account_admin"


class AuthenticationDenied(DomainError):
    code = "authentication_denied"

    def __init__(self) -> None:
        super().__init__("Authentication required.")


class OperatorAccessDenied(DomainError):
    code = "operator_access_denied"

    def __init__(self) -> None:
        super().__init__("Operator access denied.")


@dataclass(frozen=True)
class OperatorPrincipal:
    id: OperatorId
    workspace_id: WorkspaceId
    role: OperatorRole
    enabled: bool = True
    version: Version = Version(1)
    authentication_source: str = "local_token_v1"

    def __post_init__(self) -> None:
        if (
            type(self.id) is not OperatorId
            or type(self.workspace_id) is not WorkspaceId
            or type(self.role) is not OperatorRole
            or type(self.enabled) is not bool
            or type(self.version) is not Version
            or self.authentication_source != "local_token_v1"
            or len(str(self.id)) > 128
        ):
            raise InvariantViolation("operator_principal_schema")


def require_digest(value: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise InvariantViolation("operator_digest_schema")


@dataclass(frozen=True)
class OperatorAccount:
    principal: OperatorPrincipal
    credential_digest: str = field(repr=False)

    def __post_init__(self) -> None:
        require_digest(self.credential_digest)


@dataclass(frozen=True)
class OperatorSession:
    token_digest: str = field(repr=False)
    principal_id: OperatorId
    principal_version: Version
    created_at: datetime
    expires_at: datetime
    revoked: bool = False

    def __post_init__(self) -> None:
        require_digest(self.token_digest)
        require_utc(self.created_at, "created_at")
        require_utc(self.expires_at, "expires_at")
        if (
            type(self.principal_id) is not OperatorId
            or type(self.principal_version) is not Version
            or type(self.revoked) is not bool
            or not 0 < (self.expires_at - self.created_at).total_seconds() <= 3600
        ):
            raise InvariantViolation("operator_session_schema")


@dataclass(frozen=True)
class OperatorAudit:
    principal_id: OperatorId
    workspace_id: WorkspaceId
    command: str
    target_id: OperatorId
    timestamp: datetime

    def __post_init__(self) -> None:
        require_utc(self.timestamp, "timestamp")
        if self.command not in {
            "local_provision",
            "session_created",
            "session_revoked",
            "disabled",
        }:
            raise InvariantViolation("operator_audit_command")


class OperatorPolicy:
    """Pure policy; application boundaries must first resolve an authenticated session."""

    @staticmethod
    def require(
        principal: OperatorPrincipal, workspace: WorkspaceId, resource: OperatorResource
    ) -> None:
        if (
            not principal.enabled
            or type(workspace) is not WorkspaceId
            or principal.workspace_id != workspace
            or type(resource) is not OperatorResource
        ):
            raise OperatorAccessDenied()
        allowed = {OperatorResource.OPERATIONAL}
        if principal.role in {OperatorRole.AUDITOR, OperatorRole.OPERATOR, OperatorRole.ADMIN}:
            allowed |= {OperatorResource.AUDIT, OperatorResource.RECOVERY}
        if principal.role is OperatorRole.ADMIN:
            allowed.add(OperatorResource.ACCOUNT_ADMIN)
        # Even admin cannot export sensitive content or execute/approve agent actions.
        if resource not in allowed:
            raise OperatorAccessDenied()
