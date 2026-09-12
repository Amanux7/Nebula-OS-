"""Explicit migration lifecycle. Opening a store never creates canonical tables."""

import sqlite3
from hashlib import sha256
from pathlib import Path

from agent_company_os.domain.errors import InvariantViolation


def _migration() -> str:
    return Path(__file__).with_name("migrations").joinpath("001_domain.sql").read_text("utf-8")


def migrate_database(path: Path) -> None:
    """Explicit trusted-host bootstrap; unknown/modified schema history fails closed."""
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        script = _migration()
        checksum = sha256(script.encode()).hexdigest()
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if exists:
            if connection.execute("SELECT version,checksum FROM schema_migrations").fetchall() != [
                (1, checksum)
            ]:
                raise InvariantViolation("unsupported_database_migration")
            return
        # executescript is used ONLY for the shipped, trusted migration. Never caller SQL.
        connection.executescript("BEGIN IMMEDIATE;\n" + script)
        connection.execute("INSERT INTO schema_migrations VALUES (?,?)", (1, checksum))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def open_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=rw", uri=True, isolation_level=None
    )
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        expected = [(1, sha256(_migration().encode()).hexdigest())]
        if (
            connection.execute("SELECT version,checksum FROM schema_migrations").fetchall()
            != expected
        ):
            raise InvariantViolation("unsupported_database_migration")
        return connection
    except BaseException:
        connection.close()
        raise
