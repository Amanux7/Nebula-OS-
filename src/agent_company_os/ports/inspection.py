"""Bounded, redacted inspection records; not a generic object/SQL interface."""

from dataclasses import dataclass
from typing import Protocol

from agent_company_os.domain.ids import WorkspaceId


@dataclass(frozen=True)
class InspectionRecord:
    id: str
    kind: str
    fields: tuple[tuple[str, str], ...]


class InspectionCatalog(Protocol):
    def records(self, workspace: WorkspaceId, kind: str) -> tuple[InspectionRecord, ...]: ...
