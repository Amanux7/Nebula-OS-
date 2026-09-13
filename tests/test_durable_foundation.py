"""Direct checkpoint tests, independent of runtime wiring."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_company_os.adapters.durable_codec import decode_record, encode_record
from agent_company_os.adapters.sqlite_database import migrate_database, open_database
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.ids import WorkspaceId
from agent_company_os.domain.workspace import Workspace


def workspace() -> Workspace:
    return Workspace.create(
        WorkspaceId("workspace-fixture"), "Fixture", datetime(2026, 9, 12, tzinfo=UTC)
    )


def insert_workspace(connection: sqlite3.Connection) -> None:
    record = workspace()
    connection.execute(
        "INSERT INTO domain_records(kind,id,workspace_id,version,status,created_at,updated_at,payload) "
        "VALUES ('workspace',?,?,1,'active',?,?,?)",
        (
            str(record.id),
            str(record.id),
            record.created_at.isoformat(),
            record.updated_at.isoformat(),
            encode_record(record),
        ),
    )


def test_bootstrap_once_reopen_and_foreign_keys(tmp_path: Path) -> None:
    path = tmp_path / "canonical.sqlite"
    migrate_database(path)
    migrate_database(path)
    with open_database(path) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert connection.execute("SELECT version FROM schema_migrations").fetchall() == [
            (1,),
            (2,),
        ]
        connection.execute("BEGIN IMMEDIATE")
        insert_workspace(connection)
        connection.commit()
    connection.close()
    reopened = open_database(path)
    try:
        payload = reopened.execute("SELECT payload FROM domain_records").fetchone()[0]
        assert decode_record(payload, Workspace) == workspace()
    finally:
        reopened.close()


def test_explicit_transaction_rollback(tmp_path: Path) -> None:
    path = tmp_path / "rollback.sqlite"
    migrate_database(path)
    connection = open_database(path)
    connection.execute("BEGIN IMMEDIATE")
    insert_workspace(connection)
    connection.rollback()
    connection.close()
    reopened = open_database(path)
    assert reopened.execute("SELECT count(*) FROM domain_records").fetchone() == (0,)
    reopened.close()


def test_open_does_not_bootstrap(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        open_database(path)
    assert not path.exists()


def test_unknown_migration_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "unknown.sqlite"
    migrate_database(path)
    connection = open_database(path)
    connection.execute("UPDATE schema_migrations SET checksum='corrupt'")
    connection.close()
    with pytest.raises(InvariantViolation):
        open_database(path)
    with pytest.raises(InvariantViolation):
        migrate_database(path)


def test_foreign_lineage_is_not_insertable(tmp_path: Path) -> None:
    path = tmp_path / "scope.sqlite"
    migrate_database(path)
    connection = open_database(path)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO domain_records(kind,id,workspace_id,version,status,created_at,updated_at,payload) "
            "VALUES ('goal','g','missing',1,'draft','t','t','{}')"
        )
    connection.close()


def test_codec_round_trip() -> None:
    original = workspace()
    assert decode_record(encode_record(original), Workspace) == original
    assert encode_record(original) == encode_record(original)


@pytest.mark.parametrize(
    "mutation", ["schema", "type", "enum", "missing", "extra", "bool_version", "time", "id"]
)
def test_codec_rejects_corruption(mutation: str) -> None:
    data = json.loads(encode_record(workspace()))
    match mutation:
        case "schema":
            data["schema_version"] = 999
        case "type":
            data["type"] = "AgentRun"
        case "enum":
            data["payload"]["status"] = "unknown"
        case "missing":
            del data["payload"]["name"]
        case "extra":
            data["payload"]["permission"] = "all"
        case "bool_version":
            data["payload"]["version"]["value"] = True
        case "time":
            data["payload"]["created_at"] = "2026-09-12T00:00:00"
        case "id":
            data["payload"]["id"]["value"] = ""
    with pytest.raises(InvariantViolation):
        decode_record(json.dumps(data), Workspace)


@pytest.mark.parametrize("raw", ["{", "null", "[]", '{"type":"Workspace","type":"Goal"}'])
def test_malformed_codec_input(raw: str) -> None:
    with pytest.raises(InvariantViolation):
        decode_record(raw, Workspace)
