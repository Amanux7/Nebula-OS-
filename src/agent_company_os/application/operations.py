"""Authenticated modes. Releasing a workspace never releases restored intent holds."""

from agent_company_os.application.operator import OperatorService
from agent_company_os.application.recovery import RecoveryService
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.ids import WorkspaceId
from agent_company_os.domain.operations import (
    OperationalMode,
    ReleaseAudit,
    ReleaseResult,
    RestoreContext,
)
from agent_company_os.domain.operator import OperatorAccessDenied, OperatorResource, OperatorRole
from agent_company_os.ports.operations import OperationalModeStore


class OperationalModeService:
    def __init__(
        self,
        operators: OperatorService,
        store: OperationalModeStore,
        recovery: RecoveryService | None = None,
    ) -> None:
        self.operators, self.store = operators, store
        self.recovery = recovery

    def context(self, token: str, workspace: WorkspaceId) -> RestoreContext | None:
        with self.operators.store.atomic():
            self.operators.authorize(token, workspace, OperatorResource.RECOVERY)
            return self.store.restore_context(workspace)

    def audit(self, token: str, workspace: WorkspaceId) -> tuple[ReleaseAudit, ...]:
        with self.operators.store.atomic():
            self.operators.authorize(token, workspace, OperatorResource.AUDIT)
            return self.store.release_audit(workspace)

    def release(self, token: str, workspace: WorkspaceId) -> ReleaseResult:
        with self.operators.store.atomic():
            principal = self.operators.principal(token)
            if principal.workspace_id != workspace:
                raise OperatorAccessDenied()
            if self.recovery is None:
                raise InvariantViolation("release_recovery_binding_missing")
            recovery = self.recovery
            return self.store.release(
                workspace,
                str(principal.id),
                self.operators.clock.now(),
                lambda: recovery.classify(workspace),
                principal.role is OperatorRole.ADMIN,
            )

    def status(self, token: str, workspace: WorkspaceId) -> OperationalMode:
        with self.operators.store.atomic():
            self.operators.authorize(token, workspace, OperatorResource.OPERATIONAL)
            return self.store.mode(workspace)

    def restrict(self, token: str, workspace: WorkspaceId, mode: OperationalMode) -> None:
        with self.operators.store.atomic():
            principal = self.operators.authorize(token, workspace, OperatorResource.ACCOUNT_ADMIN)
            self.store.restrict(workspace, mode, str(principal.id), self.operators.clock.now())
