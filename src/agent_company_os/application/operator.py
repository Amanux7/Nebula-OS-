"""Authenticate bearer secrets before resolving canonical operator authority.

Provisioning is a trusted local bootstrap operation, never a public API endpoint.
Credentials and sessions have separate namespaces and cannot substitute for each other.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from hashlib import sha256

from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.operator import (
    AuthenticationDenied,
    OperatorAccessDenied,
    OperatorAccount,
    OperatorAudit,
    OperatorId,
    OperatorPolicy,
    OperatorPrincipal,
    OperatorResource,
    OperatorRole,
    OperatorSession,
)
from agent_company_os.ports.clock import Clock
from agent_company_os.ports.operator import OperatorSecrets, OperatorStore
from agent_company_os.ports.store import DomainStore


@dataclass(frozen=True)
class IssuedOperatorSecret:
    """One-time return to a trusted caller; never include in logs or normal DTOs."""

    value: str = field(repr=False)


def _digest(value: str, purpose: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise AuthenticationDenied()
    return sha256((purpose + ":" + value).encode("ascii")).hexdigest()


class OperatorService:
    def principal(self, token: str) -> OperatorPrincipal:
        """Resolve current server-side identity; callers cannot submit a principal."""
        with self.store.atomic():
            return self._principal(token)

    def __init__(
        self,
        store: OperatorStore,
        domain: DomainStore,
        clock: Clock,
        secrets: OperatorSecrets,
        session_seconds: int = 900,
    ) -> None:
        if type(session_seconds) is not int or not 1 <= session_seconds <= 3600:
            raise InvariantViolation("operator_session_duration")
        self.store, self.domain, self.clock, self.secrets = store, domain, clock, secrets
        self.session_seconds = session_seconds

    def provision_local(
        self, workspace: WorkspaceId, principal_id: OperatorId, role: OperatorRole
    ) -> IssuedOperatorSecret:
        self.domain.get_workspace(workspace)
        principal = OperatorPrincipal(principal_id, workspace, role)
        credential = self.secrets.issue()
        with self.store.atomic():
            self.store.add_account(OperatorAccount(principal, _digest(credential, "credential")))
            self.store.append_audit(
                OperatorAudit(
                    principal_id, workspace, "local_provision", principal_id, self.clock.now()
                )
            )
        return IssuedOperatorSecret(credential)

    def login(self, credential: str) -> IssuedOperatorSecret:
        digest = _digest(credential, "credential")
        with self.store.atomic():
            account = self.store.credential(digest)
            if account is None or not account.principal.enabled:
                raise AuthenticationDenied()
            principal = account.principal
            now = self.clock.now()
            token = self.secrets.issue()
            self.store.add_session(
                OperatorSession(
                    _digest(token, "session"),
                    principal.id,
                    principal.version,
                    now,
                    now + timedelta(seconds=self.session_seconds),
                )
            )
            self.store.append_audit(
                OperatorAudit(
                    principal.id, principal.workspace_id, "session_created", principal.id, now
                )
            )
        return IssuedOperatorSecret(token)

    def _principal(self, token: str) -> OperatorPrincipal:
        session = self.store.session(_digest(token, "session"))
        if (
            session is None
            or session.revoked
            or not session.created_at <= self.clock.now() < session.expires_at
        ):
            raise AuthenticationDenied()
        account = self.store.account(session.principal_id)
        if (
            account is None
            or not account.principal.enabled
            or account.principal.version != session.principal_version
        ):
            raise AuthenticationDenied()
        return account.principal

    def authorize(
        self, token: str, workspace: WorkspaceId, resource: OperatorResource
    ) -> OperatorPrincipal:
        with self.store.atomic():
            principal = self._principal(token)
            OperatorPolicy.require(principal, workspace, resource)
            return principal

    def logout(self, token: str) -> None:
        with self.store.atomic():
            principal = self._principal(token)
            self.store.revoke_session(_digest(token, "session"))
            self.store.append_audit(
                OperatorAudit(
                    principal.id,
                    principal.workspace_id,
                    "session_revoked",
                    principal.id,
                    self.clock.now(),
                )
            )

    def disable(
        self, token: str, workspace: WorkspaceId, target: OperatorId, expected: Version
    ) -> None:
        with self.store.atomic():
            principal = self._principal(token)
            OperatorPolicy.require(principal, workspace, OperatorResource.ACCOUNT_ADMIN)
            account = self.store.account(target)
            if account is None or account.principal.workspace_id != workspace:
                raise OperatorAccessDenied()
            self.store.disable(target, expected)
            self.store.append_audit(
                OperatorAudit(principal.id, workspace, "disabled", target, self.clock.now())
            )

    def audit(self, token: str, workspace: WorkspaceId) -> tuple[OperatorAudit, ...]:
        with self.store.atomic():
            principal = self._principal(token)
            OperatorPolicy.require(principal, workspace, OperatorResource.AUDIT)
            return self.store.audit(workspace)
