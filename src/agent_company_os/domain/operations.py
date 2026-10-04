"""Operational safety state is independent of agent authority."""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class RestoreContext:
    generation: int
    backup_id: str
    backup_digest: str
    restored_at: str
    manifest_schema_version: int
    principal_id: str
    held_intent_ids: tuple[str, ...]


@dataclass(frozen=True)
class ReleaseResult:
    success: bool
    reason: str
    mode: str
    generation: int | None
    recovery_count: int
    held_intent_count: int


@dataclass(frozen=True)
class ReleaseAudit:
    principal_id: str
    generation: int | None
    timestamp: str
    previous_mode: str
    new_mode: str
    success: bool
    reason: str
    recovery_count: int
    held_intent_count: int


class OperationalMode(StrEnum):
    NORMAL = "normal"
    MAINTENANCE = "maintenance"
    RESTORE_QUARANTINE = "restore_quarantine"
