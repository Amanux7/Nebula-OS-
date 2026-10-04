"""Bounded, redacted inspection records; not a generic object/SQL interface."""

from dataclasses import dataclass
from typing import Protocol

from agent_company_os.domain.ids import WorkspaceId


@dataclass(frozen=True)
class InspectionLink:
    label: str
    kind: str
    id: str


@dataclass(frozen=True)
class InspectionRecord:
    id: str
    kind: str
    fields: tuple[tuple[str, str], ...]
    links: tuple[InspectionLink, ...] = ()


@dataclass(frozen=True)
class LineageSection:
    kind: str
    records: tuple[InspectionRecord, ...]
    truncated: bool = False


@dataclass(frozen=True)
class InspectionLineage:
    root: InspectionRecord
    sections: tuple[LineageSection, ...]


class InspectionCatalog(Protocol):
    def records(self, workspace: WorkspaceId, kind: str) -> tuple[InspectionRecord, ...]: ...
