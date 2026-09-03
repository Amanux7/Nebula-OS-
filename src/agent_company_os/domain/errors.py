"""Small structured error model for deterministic domain failures."""

from __future__ import annotations

from collections.abc import Mapping


class DomainError(Exception):
    """Base error carrying a stable code and serialization-safe details."""

    code = "domain_error"

    def __init__(self, message: str, *, details: Mapping[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message, "details": dict(self.details)}


class InvalidStateTransition(DomainError):
    code = "invalid_state_transition"

    def __init__(
        self,
        entity_type: str,
        entity_id: str,
        current_status: str,
        target_status: str,
    ) -> None:
        super().__init__(
            f"Cannot transition {entity_type} {entity_id} from "
            f"{current_status} to {target_status}.",
            details={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "current_status": current_status,
                "target_status": target_status,
            },
        )


class WorkspaceMismatch(DomainError):
    code = "workspace_mismatch"

    def __init__(
        self,
        relationship: str,
        expected_workspace_id: str,
        actual_workspace_id: str,
    ) -> None:
        super().__init__(
            f"Cross-workspace relationship rejected for {relationship}.",
            details={
                "relationship": relationship,
                "expected_workspace_id": expected_workspace_id,
                "actual_workspace_id": actual_workspace_id,
            },
        )


class EntityNotFound(DomainError):
    code = "entity_not_found"

    def __init__(self, entity_type: str, entity_id: str) -> None:
        super().__init__(
            f"{entity_type} {entity_id} was not found.",
            details={"entity_type": entity_type, "entity_id": entity_id},
        )


class VersionConflict(DomainError):
    code = "version_conflict"

    def __init__(
        self,
        entity_type: str,
        entity_id: str,
        expected_version: int,
        actual_version: int,
    ) -> None:
        super().__init__(
            f"Version conflict for {entity_type} {entity_id}: expected "
            f"{expected_version}, actual {actual_version}.",
            details={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "expected_version": str(expected_version),
                "actual_version": str(actual_version),
            },
        )


class InvariantViolation(DomainError):
    code = "invariant_violation"

    def __init__(
        self,
        rule: str,
        *,
        details: Mapping[str, str] | None = None,
    ) -> None:
        merged_details = {"rule": rule, **dict(details or {})}
        super().__init__(f"Domain invariant violated: {rule}.", details=merged_details)
