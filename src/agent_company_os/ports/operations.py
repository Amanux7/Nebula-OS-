"""Used safety-mode storage boundary; no database types escape it."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from agent_company_os.domain.ids import WorkspaceId
from agent_company_os.domain.operations import (
    OperationalMode,
    ReleaseAudit,
    ReleaseResult,
    RestoreContext,
)
from agent_company_os.domain.recovery import RecoveryCase


class OperationalModeStore(Protocol):
    def restore_context(self, workspace: WorkspaceId) -> RestoreContext | None: ...
    def release_audit(self, workspace: WorkspaceId) -> tuple[ReleaseAudit, ...]: ...
    def release(
        self,
        workspace: WorkspaceId,
        principal: str,
        at: datetime,
        classify: Callable[[], tuple[RecoveryCase, ...]],
        authorized: bool,
    ) -> ReleaseResult: ...
    def mode(self, workspace: WorkspaceId) -> OperationalMode: ...
    def restrict(
        self, workspace: WorkspaceId, mode: OperationalMode, principal: str, at: datetime
    ) -> None: ...
