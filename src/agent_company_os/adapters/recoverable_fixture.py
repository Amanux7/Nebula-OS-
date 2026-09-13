"""Offline remote ledger, deliberately independent of application transactions."""

import sqlite3
from hashlib import sha256
from pathlib import Path

from agent_company_os.adapters.tool_executors import output_json
from agent_company_os.application.tool_validation import input_json
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.recovery import (
    ConnectorCapabilities,
    RemoteLookup,
    RemoteStatus,
    execution_key,
)
from agent_company_os.domain.tools import (
    FixtureMessageInput,
    ToolError,
    ToolFailure,
    ToolInput,
    ToolInvocation,
    ToolOutput,
)


def bootstrap_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='fixture_effects'"
        ).fetchone():
            connection.executescript(
                Path(__file__)
                .with_name("migrations")
                .joinpath("fixture_remote.sql")
                .read_text("utf-8")
            )
        connection.commit()
    finally:
        connection.close()


class RecoverableFixtureExecutor:
    capabilities = ConnectorCapabilities(True, True, False, False)

    def __init__(self, path: Path, *, unknown: bool = False, reject: bool = False) -> None:
        self.connection = sqlite3.connect(
            path.resolve().as_uri() + "?mode=rw", uri=True, isolation_level=None
        )
        self.connection.execute("PRAGMA synchronous=FULL")
        self.unknown, self.reject = unknown, reject
        self.calls = 0

    def close(self) -> None:
        self.connection.close()

    async def execute(self, request: ToolInput, context: ToolInvocation) -> str:
        if not isinstance(request, FixtureMessageInput):
            raise ToolFailure(ToolError.VALIDATION_ERROR)
        return self.dispatch(execution_key(context), request)

    def dispatch(self, key: str, request: FixtureMessageInput) -> str:
        self.calls += 1
        digest = sha256(input_json(request).encode()).hexdigest()
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            old = self.connection.execute(
                "SELECT payload_digest,status,output_json FROM fixture_effects WHERE idempotency_key=?",
                (key,),
            ).fetchone()
            if old is None:
                result = output_json(
                    ToolOutput(request.destination, (), "fixture_delivery_observed")
                )
                status = (
                    RemoteStatus.PROCESSED_FAILURE
                    if self.reject
                    else RemoteStatus.PROCESSED_SUCCESS
                )
                self.connection.execute(
                    "INSERT INTO fixture_effects VALUES (?,?,?,?,?,?)",
                    (
                        key,
                        digest,
                        request.destination,
                        request.message,
                        status.value,
                        None if self.reject else result,
                    ),
                )
            else:
                if old[0] != digest:
                    raise InvariantViolation("remote_idempotency_payload_mismatch")
                status, result = RemoteStatus(old[1]), old[2]
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise
        if status is RemoteStatus.PROCESSED_FAILURE:
            raise ToolFailure(ToolError.REJECTED)
        return str(result)

    async def lookup_status(self, idempotency_key: str) -> RemoteLookup:
        if self.unknown:
            return RemoteLookup(RemoteStatus.UNKNOWN)
        row = self.connection.execute(
            "SELECT status,output_json FROM fixture_effects WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        return (
            RemoteLookup(RemoteStatus(row[0]), row[1])
            if row
            else RemoteLookup(RemoteStatus.NEVER_RECEIVED)
        )

    def effect_count(self) -> int:
        return int(
            self.connection.execute(
                "SELECT count(*) FROM fixture_effects WHERE status='processed_success'"
            ).fetchone()[0]
        )
