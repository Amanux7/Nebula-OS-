"""Authenticated, scoped backup commands; restoring never releases quarantine."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from agent_company_os.application.operator import OperatorService
from agent_company_os.domain.ids import WorkspaceId
from agent_company_os.domain.operator import OperatorResource


@dataclass(frozen=True)
class BackupManifest:
    backup_id: str
    created_at: str
    schema_version: int
    sha256: str
    workspace_id: str
    application_version: str = "0.1.0"
    format_version: int = 1


class BackupPort(Protocol):
    def create(self, name: str, workspace: WorkspaceId, at: datetime) -> BackupManifest: ...
    def restore(
        self, name: str, destination: str, workspace: WorkspaceId, principal: str, at: datetime
    ) -> BackupManifest: ...


class BackupService:
    def __init__(self, operators: OperatorService, backups: BackupPort) -> None:
        self.operators, self.backups = operators, backups

    def create(self, token: str, workspace: WorkspaceId, name: str) -> BackupManifest:
        with self.operators.store.atomic():
            self.operators.authorize(token, workspace, OperatorResource.ACCOUNT_ADMIN)
            return self.backups.create(name, workspace, self.operators.clock.now())

    def restore(
        self, token: str, workspace: WorkspaceId, name: str, destination: str
    ) -> BackupManifest:
        with self.operators.store.atomic():
            principal = self.operators.authorize(token, workspace, OperatorResource.ACCOUNT_ADMIN)
            return self.backups.restore(
                name, destination, workspace, str(principal.id), self.operators.clock.now()
            )
