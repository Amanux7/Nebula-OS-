"""Used safety-mode storage boundary; no database types escape it."""

from datetime import datetime
from typing import Protocol

from agent_company_os.domain.ids import WorkspaceId
from agent_company_os.domain.operations import OperationalMode


class OperationalModeStore(Protocol):
    def mode(self, workspace: WorkspaceId) -> OperationalMode: ...
    def restrict(
        self, workspace: WorkspaceId, mode: OperationalMode, principal: str, at: datetime
    ) -> None: ...
