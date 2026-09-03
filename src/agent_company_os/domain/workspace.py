"""Minimal Workspace tenancy aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.validation import clean_required_text, require_utc


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"


@dataclass(frozen=True, slots=True)
class Workspace:
    id: WorkspaceId
    name: str
    status: WorkspaceStatus
    version: Version
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        clean_required_text(self.name, "name")
        require_utc(self.created_at, "created_at")
        require_utc(self.updated_at, "updated_at")

    @classmethod
    def create(cls, workspace_id: WorkspaceId, name: str, created_at: datetime) -> Workspace:
        return cls(
            id=workspace_id,
            name=clean_required_text(name, "name"),
            status=WorkspaceStatus.ACTIVE,
            version=Version.initial(),
            created_at=created_at,
            updated_at=created_at,
        )
