"""Explicit migration lifecycle. Opening a store never creates canonical tables."""

import sqlite3
from hashlib import sha256
from pathlib import Path

from agent_company_os.domain.errors import InvariantViolation


def _migrations() -> tuple[str, ...]:
    root = Path(__file__).with_name("migrations")
    return tuple(
        root.joinpath(name).read_text("utf-8") for name in ("001_domain.sql", "002_runtime.sql")
    )


def _expected() -> list[tuple[int, str]]:
    return [
        (number, sha256(script.encode()).hexdigest())
        for number, script in enumerate(_migrations(), 1)
    ]


def migrate_database(path: Path) -> None:
    """Explicit trusted-host bootstrap; unknown/modified schema history fails closed."""
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        history = (
            connection.execute(
                "SELECT version,checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
            if exists
            else []
        )
        expected = _expected()
        if history != expected[: len(history)] or len(history) > len(expected):
            raise InvariantViolation("unsupported_database_migration")
        for number, script in enumerate(_migrations(), 1):
            if number <= len(history):
                continue
            statement = ""
            for line in script.splitlines(keepends=True):
                statement += line
                if sqlite3.complete_statement(statement):
                    connection.execute(statement)
                    statement = ""
            connection.execute("INSERT INTO schema_migrations VALUES (?,?)", expected[number - 1])
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
        expected = _expected()
        if (
            connection.execute(
                "SELECT version,checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
            != expected
        ):
            raise InvariantViolation("unsupported_database_migration")
        return connection
    except BaseException:
        connection.close()
        raise
