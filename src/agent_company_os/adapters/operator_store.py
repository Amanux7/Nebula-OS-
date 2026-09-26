"""Local identity database, intentionally outside canonical backup/restore scope.

One connection per host worker. Parameterized SQL never crosses the adapter boundary.
Only SHA-256 digests of generated 256-bit secrets are persisted; not password hashes.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from secrets import token_hex

from agent_company_os.domain.errors import InvariantViolation, VersionConflict
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.operator import (
    OperatorAccount,
    OperatorAudit,
    OperatorId,
    OperatorPrincipal,
    OperatorRole,
    OperatorSession,
)


class SecureOperatorSecrets:
    def issue(self) -> str:
        return token_hex(32)


def _schema() -> str:
    return Path(__file__).with_name("migrations").joinpath("operator_001.sql").read_text("utf-8")


def migrate_operator_database(path: Path) -> None:
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        script = _schema()
        checksum = sha256(script.encode()).hexdigest()
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='operator_schema' AND type='table'"
        ).fetchone():
            if connection.execute("SELECT version,checksum FROM operator_schema").fetchall() != [
                (1, checksum)
            ]:
                raise InvariantViolation("operator_schema_incompatible")
        else:
            # Do not accidentally initialize identity tables inside a canonical database.
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                raise InvariantViolation("operator_database_must_be_separate")
            statement = ""
            for line in script.splitlines(keepends=True):
                statement += line
                if sqlite3.complete_statement(statement):
                    connection.execute(statement)
                    statement = ""
            connection.execute("INSERT INTO operator_schema VALUES (1,?)", (checksum,))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


class SqliteOperatorStore:
    def __init__(self, path: Path) -> None:
        self.connection = sqlite3.connect(
            path.resolve().as_uri() + "?mode=rw", uri=True, isolation_level=None
        )
        self._depth = 0
        try:
            self.connection.execute("PRAGMA foreign_keys=ON")
            self.connection.execute("PRAGMA synchronous=FULL")
            if self.connection.execute(
                "SELECT version,checksum FROM operator_schema"
            ).fetchall() != [(1, sha256(_schema().encode()).hexdigest())]:
                raise InvariantViolation("operator_schema_incompatible")
        except BaseException:
            self.connection.close()
            raise

    def close(self) -> None:
        if self._depth:
            raise InvariantViolation("operator_transaction_active")
        self.connection.close()

    @contextmanager
    def atomic(self) -> Iterator[None]:
        depth = self._depth
        self.connection.execute("BEGIN IMMEDIATE" if depth == 0 else f"SAVEPOINT operator_{depth}")
        self._depth += 1
        try:
            yield
            if depth == 0:
                self.connection.commit()
            else:
                self.connection.execute(f"RELEASE operator_{depth}")
        except BaseException:
            if depth == 0:
                self.connection.rollback()
            else:
                self.connection.execute(f"ROLLBACK TO operator_{depth}")
                self.connection.execute(f"RELEASE operator_{depth}")
            raise
        finally:
            self._depth -= 1

    @staticmethod
    def _account(row: tuple[object, ...] | None) -> OperatorAccount | None:
        if row is None:
            return None
        identity, workspace, role, enabled, version, digest = row
        if (
            type(identity) is not str
            or type(workspace) is not str
            or type(role) is not str
            or type(enabled) is not int
            or enabled not in (0, 1)
            or type(version) is not int
            or type(digest) is not str
        ):
            raise InvariantViolation("corrupt_operator_account")
        try:
            return OperatorAccount(
                OperatorPrincipal(
                    OperatorId(identity),
                    WorkspaceId(workspace),
                    OperatorRole(role),
                    bool(enabled),
                    Version(version),
                ),
                digest,
            )
        except ValueError:
            raise InvariantViolation("corrupt_operator_account") from None

    def add_account(self, account: OperatorAccount) -> None:
        p = account.principal
        self.connection.execute(
            "INSERT INTO operator_accounts VALUES (?,?,?,?,?,?)",
            (
                str(p.id),
                str(p.workspace_id),
                p.role.value,
                int(p.enabled),
                p.version.value,
                account.credential_digest,
            ),
        )

    def account(self, principal_id: OperatorId) -> OperatorAccount | None:
        return self._account(
            self.connection.execute(
                "SELECT * FROM operator_accounts WHERE id=?", (str(principal_id),)
            ).fetchone()
        )

    def credential(self, digest: str) -> OperatorAccount | None:
        return self._account(
            self.connection.execute(
                "SELECT * FROM operator_accounts WHERE credential_digest=?", (digest,)
            ).fetchone()
        )

    def disable(self, principal_id: OperatorId, expected: Version) -> None:
        cursor = self.connection.execute(
            "UPDATE operator_accounts SET enabled=0,version=version+1 "
            "WHERE id=? AND version=? AND enabled=1",
            (str(principal_id), expected.value),
        )
        if cursor.rowcount != 1:
            account = self.account(principal_id)
            raise VersionConflict(
                "OperatorPrincipal",
                str(principal_id),
                expected.value,
                account.principal.version.value if account else 0,
            )

    def add_session(self, session: OperatorSession) -> None:
        self.connection.execute(
            "INSERT INTO operator_sessions VALUES (?,?,?,?,?,?)",
            (
                session.token_digest,
                str(session.principal_id),
                session.principal_version.value,
                session.created_at.isoformat(),
                session.expires_at.isoformat(),
                int(session.revoked),
            ),
        )

    def session(self, digest: str) -> OperatorSession | None:
        row = self.connection.execute(
            "SELECT * FROM operator_sessions WHERE digest=?", (digest,)
        ).fetchone()
        if row is None:
            return None
        token, principal, version, created, expires, revoked = row
        if (
            type(token) is not str
            or type(principal) is not str
            or type(version) is not int
            or type(created) is not str
            or type(expires) is not str
            or type(revoked) is not int
            or revoked not in (0, 1)
        ):
            raise InvariantViolation("corrupt_operator_session")
        try:
            return OperatorSession(
                token,
                OperatorId(principal),
                Version(version),
                datetime.fromisoformat(created),
                datetime.fromisoformat(expires),
                bool(revoked),
            )
        except ValueError:
            raise InvariantViolation("corrupt_operator_session") from None

    def revoke_session(self, digest: str) -> None:
        self.connection.execute("UPDATE operator_sessions SET revoked=1 WHERE digest=?", (digest,))

    def append_audit(self, event: OperatorAudit) -> None:
        for identity in (event.principal_id, event.target_id):
            account = self.account(identity)
            if account is None or account.principal.workspace_id != event.workspace_id:
                raise InvariantViolation("operator_audit_workspace")
        self.connection.execute(
            "INSERT INTO operator_audit(principal_id,workspace_id,command,target_id,timestamp) "
            "VALUES (?,?,?,?,?)",
            (
                str(event.principal_id),
                str(event.workspace_id),
                event.command,
                str(event.target_id),
                event.timestamp.isoformat(),
            ),
        )

    def audit(self, workspace: WorkspaceId) -> tuple[OperatorAudit, ...]:
        return tuple(
            OperatorAudit(
                OperatorId(row[0]),
                WorkspaceId(row[1]),
                row[2],
                OperatorId(row[3]),
                datetime.fromisoformat(row[4]),
            )
            for row in self.connection.execute(
                "SELECT principal_id,workspace_id,command,target_id,timestamp "
                "FROM operator_audit WHERE workspace_id=? ORDER BY sequence",
                (str(workspace),),
            )
        )
