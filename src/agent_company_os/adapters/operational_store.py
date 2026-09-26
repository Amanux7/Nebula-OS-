"""Safety restrictions share the canonical SQLite writer serialization point."""

from datetime import datetime

from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.ids import WorkspaceId
from agent_company_os.domain.operations import OperationalMode


class SqliteOperationalStore:
    def __init__(self, group: SqliteStoreGroup) -> None:
        self.group = group

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
