"""Plaintext local snapshots, explicit fresh restores, and persistent quarantine.

Roots are trusted host configuration, never supplied by an HTTP caller. Names are
single components. A digest detects accidental damage, not malicious replacement.
The caller must restrict root ACLs on Windows; POSIX creation modes are owner-only.
"""

import json
import re
import sqlite3
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from agent_company_os.adapters.sqlite_database import _expected, open_database
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.application.backup import BackupManifest
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.ids import WorkspaceId


def _digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _child(root: Path, name: str) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", name):
        raise InvariantViolation("invalid_backup_name")
    target = root / name
    if target.is_symlink() or target.resolve().parent != root.resolve():
        raise InvariantViolation("backup_path_escape")
    return target


class SqliteBackupAdapter:
    def __init__(self, source: Path, backups: Path, restores: Path) -> None:
        self.source, self.backups, self.restores = source, backups.resolve(), restores.resolve()
        if self.backups == self.restores:
            raise InvariantViolation("separate_backup_restore_roots_required")
        for root in (self.backups, self.restores):
            root.mkdir(mode=0o700, parents=True, exist_ok=True)

    @staticmethod
    def _scope(path: Path, workspace: WorkspaceId) -> None:
        # Decode and validate every canonical record, including cross-workspace lineage.
        group = SqliteStoreGroup(path)
        try:
            rows = group.connection.execute(
                "SELECT id FROM domain_records WHERE kind='workspace' ORDER BY id"
            ).fetchall()
            if rows != [(str(workspace),)]:
                raise InvariantViolation("backup_requires_single_authorized_workspace")
        finally:
            group.close()

    def create(self, name: str, workspace: WorkspaceId, at: datetime) -> BackupManifest:
        # Refuse an unauthorized/multi-workspace source before creating plaintext output.
        self._scope(self.source, workspace)
        directory = _child(self.backups, name)
        directory.mkdir(mode=0o700)  # exclusive; never overwrite a snapshot
        target = directory / "canonical.sqlite"
        try:
            source = open_database(self.source)
            try:
                destination = sqlite3.connect(target)
                try:
                    with destination:
                        source.backup(destination)
                finally:
                    destination.close()
            finally:
                source.close()
            target.chmod(0o600)
            # Recheck the actual snapshot, since the source may have changed meanwhile.
            self._scope(target, workspace)
            manifest = BackupManifest(
                name, at.isoformat(), len(_expected()), _digest(target), str(workspace)
            )
            manifest_path = directory / "manifest.json"
            with manifest_path.open("x", encoding="utf-8") as stream:
                json.dump(asdict(manifest), stream, sort_keys=True)
            manifest_path.chmod(0o600)
            return manifest
        except Exception:
            # A failed scope check must not leave an unowned plaintext backup.
            for name_to_remove in ("manifest.json", "canonical.sqlite"):
                (directory / name_to_remove).unlink(missing_ok=True)
            directory.rmdir()
            raise

    def restore(
        self, name: str, destination: str, workspace: WorkspaceId, principal: str, at: datetime
    ) -> BackupManifest:
        directory = _child(self.backups, name)
        manifest_path, snapshot = directory / "manifest.json", directory / "canonical.sqlite"
        if any(p.is_symlink() for p in (manifest_path, snapshot)):
            raise InvariantViolation("backup_path_escape")
        try:
            if manifest_path.stat().st_size > 4096:
                raise ValueError("manifest size")
            data = json.loads(manifest_path.read_text("utf-8"))
            manifest = BackupManifest(**data)
            if (
                type(manifest.format_version) is not int
                or manifest.format_version != 1
                or type(manifest.schema_version) is not int
                or manifest.schema_version != len(_expected())
                or manifest.backup_id != name
                or manifest.workspace_id != str(workspace)
                or manifest.sha256 != _digest(snapshot)
            ):
                raise ValueError("manifest mismatch")
        except (ValueError, TypeError, OSError):
            raise InvariantViolation("invalid_backup_manifest") from None
        self._scope(snapshot, workspace)
        target_directory = _child(self.restores, destination)
        target_directory.mkdir(mode=0o700)
        # An uncommitted restore is not a host database: publish name only after quarantine.
        staging = target_directory / "restore.incomplete"
        source = open_database(snapshot)
        try:
            connection = sqlite3.connect(staging)
            try:
                source.backup(connection)
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("BEGIN IMMEDIATE")
                previous = connection.execute(
                    "SELECT mode FROM operational_modes WHERE workspace_id=?", (str(workspace),)
                ).fetchone()
                connection.execute(
                    "INSERT INTO operational_modes(workspace_id,mode,version) "
                    "VALUES(?,'restore_quarantine',1) ON CONFLICT(workspace_id) "
                    "DO UPDATE SET mode='restore_quarantine',version=version+1",
                    (str(workspace),),
                )
                connection.execute(
                    "INSERT INTO operational_audit"
                    "(workspace_id,principal_id,previous_mode,mode,timestamp,reason) "
                    "VALUES(?,?,?,'restore_quarantine',?,'canonical_restore')",
                    (
                        str(workspace),
                        principal,
                        previous[0] if previous else "normal",
                        at.isoformat(),
                    ),
                )
                connection.commit()
            finally:
                connection.close()
        finally:
            source.close()
        staging.chmod(0o600)
        self._scope(staging, workspace)
        staging.rename(target_directory / "canonical.sqlite")
        return manifest
