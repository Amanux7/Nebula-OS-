"""Authenticated restrictive commands. There is deliberately no release shortcut."""

from agent_company_os.application.operator import OperatorService
from agent_company_os.domain.ids import WorkspaceId
from agent_company_os.domain.operations import OperationalMode
from agent_company_os.domain.operator import OperatorResource
from agent_company_os.ports.operations import OperationalModeStore


class OperationalModeService:
    def __init__(self, operators: OperatorService, store: OperationalModeStore) -> None:
        self.operators, self.store = operators, store

    def status(self, token: str, workspace: WorkspaceId) -> OperationalMode:
        with self.operators.store.atomic():
            self.operators.authorize(token, workspace, OperatorResource.OPERATIONAL)
            return self.store.mode(workspace)

    def restrict(self, token: str, workspace: WorkspaceId, mode: OperationalMode) -> None:
        with self.operators.store.atomic():
            principal = self.operators.authorize(token, workspace, OperatorResource.ACCOUNT_ADMIN)
            self.store.restrict(workspace, mode, str(principal.id), self.operators.clock.now())
