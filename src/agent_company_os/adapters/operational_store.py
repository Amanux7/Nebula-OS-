"""Safety restrictions share the canonical SQLite writer serialization point."""

import json
from collections.abc import Callable
from datetime import datetime

from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.domain.errors import DomainError, InvariantViolation
from agent_company_os.domain.ids import WorkspaceId
from agent_company_os.domain.operations import (
    OperationalMode,
    ReleaseAudit,
    ReleaseResult,
    RestoreContext,
)
from agent_company_os.domain.recovery import RecoveryCase


class SqliteOperationalStore:
    def __init__(self, group: SqliteStoreGroup) -> None:
        self.group = group

    def restore_context(self, workspace: WorkspaceId) -> RestoreContext | None:
        with self.group.transaction():
            self.group.domain.get_workspace(workspace)
            row = self.group.connection.execute(
                "SELECT generation,backup_id,backup_digest,restored_at,manifest_json,principal_id "
                "FROM restore_incidents WHERE workspace_id=? ORDER BY generation DESC LIMIT 1",
                (str(workspace),),
            ).fetchone()
            if row is None:
                return None
            holds = self.group.connection.execute(
                "SELECT intent_id FROM restored_intent_holds "
                "WHERE workspace_id=? ORDER BY intent_id",
                (str(workspace),),
            ).fetchall()
            return RestoreContext(
                row[0],
                row[1],
                row[2],
                row[3],
                json.loads(row[4])["schema_version"],
                row[5],
                tuple(item[0] for item in holds),
            )

    def release_audit(self, workspace: WorkspaceId) -> tuple[ReleaseAudit, ...]:
        with self.group.transaction():
            self.group.domain.get_workspace(workspace)
            rows = self.group.connection.execute(
                "SELECT principal_id,generation,timestamp,previous_mode,new_mode,success,reason,"
                "recovery_count,held_intent_count FROM quarantine_release_audit "
                "WHERE workspace_id=? ORDER BY sequence DESC LIMIT 100",
                (str(workspace),),
            ).fetchall()
            return tuple(
                ReleaseAudit(
                    row[0], row[1], row[2], row[3], row[4], bool(row[5]), row[6], row[7], row[8]
                )
                for row in rows
            )

    def release(
        self,
        workspace: WorkspaceId,
        principal: str,
        at: datetime,
        classify: Callable[[], tuple[RecoveryCase, ...]],
        authorized: bool,
    ) -> ReleaseResult:
        with self.group.transaction():
            previous = self.mode(workspace)
            context = self.restore_context(workspace)
            reason = "validated_with_restored_intents_held"
            cases: tuple[RecoveryCase, ...] = ()
            if not authorized:
                reason = "admin_required"
            elif previous is not OperationalMode.RESTORE_QUARANTINE:
                reason = "not_quarantined"
            elif context is None:
                reason = "restore_provenance_missing"
            elif self.group.connection.execute("PRAGMA quick_check").fetchall() != [("ok",)] or (
                self.group.connection.execute("PRAGMA foreign_key_check").fetchall()
            ):
                reason = "integrity_failed"
            else:
                try:
                    cases = classify()  # Same transaction as the mode transition.
                except DomainError:
                    reason = "classification_failed"
                if any(
                    not self.group.runtime.intent_held(workspace, g.intent.id)
                    for g in self.group.runtime.governed_actions(workspace)
                ):
                    reason = "unfenced_consequential_intent"
            success = reason == "validated_with_restored_intents_held"
            current = OperationalMode.NORMAL if success else previous
            if success:
                self.group.connection.execute(
                    "UPDATE operational_modes SET mode='normal',version=version+1 "
                    "WHERE workspace_id=? AND mode='restore_quarantine'",
                    (str(workspace),),
                )
            generation = context.generation if context else None
            held = len(context.held_intent_ids) if context else 0
            self.group.connection.execute(
                "INSERT INTO quarantine_release_audit(workspace_id,principal_id,generation,"
                "timestamp,previous_mode,new_mode,success,reason,recovery_count,held_intent_count) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    str(workspace),
                    principal,
                    generation,
                    at.isoformat(),
                    previous.value,
                    current.value,
                    int(success),
                    reason,
                    len(cases),
                    held,
                ),
            )
            return ReleaseResult(success, reason, current.value, generation, len(cases), held)

    def mode(self, workspace: WorkspaceId) -> OperationalMode:
        with self.group.transaction():
            self.group.domain.get_workspace(workspace)
            row = self.group.connection.execute(
                "SELECT mode FROM operational_modes WHERE workspace_id=?", (str(workspace),)
            ).fetchone()
            try:
                return OperationalMode(row[0]) if row else OperationalMode.NORMAL
            except ValueError:
                raise InvariantViolation("invalid_operational_mode") from None

    def restrict(
        self, workspace: WorkspaceId, mode: OperationalMode, principal: str, at: datetime
    ) -> None:
        if mode not in (OperationalMode.MAINTENANCE, OperationalMode.RESTORE_QUARANTINE):
            raise InvariantViolation("operational_release_not_supported")
        with self.group.transaction():
            previous = self.mode(workspace)
            if previous is OperationalMode.RESTORE_QUARANTINE and mode is not previous:
                raise InvariantViolation("quarantine_release_not_supported")
            self.group.connection.execute(
                "INSERT INTO operational_modes(workspace_id,mode,version) VALUES(?,?,1) "
                "ON CONFLICT(workspace_id) DO UPDATE SET mode=excluded.mode,version=version+1",
                (str(workspace), mode.value),
            )
            self.group.connection.execute(
                "INSERT INTO operational_audit"
                "(workspace_id,principal_id,previous_mode,mode,timestamp,reason) "
                "VALUES(?,?,?,?,?,?)",
                (
                    str(workspace),
                    principal,
                    previous.value,
                    mode.value,
                    at.isoformat(),
                    "operator_command",
                ),
            )
