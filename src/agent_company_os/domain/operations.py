"""Operational safety state is independent of agent authority."""

from enum import StrEnum


class OperationalMode(StrEnum):
    NORMAL = "normal"
    MAINTENANCE = "maintenance"
    RESTORE_QUARANTINE = "restore_quarantine"
