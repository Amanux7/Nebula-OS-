"""Stage 11 durable safety controls on genuinely reopened SQLite stores."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_company_os.adapters.clocks import FakeClock
from agent_company_os.adapters.ids import DeterministicIdGenerator
from agent_company_os.adapters.operational_store import SqliteOperationalStore
from agent_company_os.adapters.operator_store import SqliteOperatorStore, migrate_operator_database
from agent_company_os.adapters.sqlite_backup import SqliteBackupAdapter
from agent_company_os.adapters.sqlite_database import migrate_database
from agent_company_os.adapters.sqlite_inspection import SqliteInspectionCatalog
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.application.backup import BackupService
from agent_company_os.application.operations import OperationalModeService
from agent_company_os.application.operator import OperatorService
from agent_company_os.application.service import CreateGoalCommand, DomainService
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.operations import OperationalMode
from agent_company_os.domain.operator import OperatorId, OperatorRole
from test_operator import TestSecrets


def test_migration_mode_and_read_only_inspection(tmp_path: Path) -> None:
    path = tmp_path / "canonical.sqlite"
    migrate_database(path)
    migrate_database(path)
    group = SqliteStoreGroup(path)
    clock = FakeClock(datetime(2026, 9, 21, tzinfo=UTC))
    domain = DomainService(group.domain, clock, DeterministicIdGenerator("ops"))
    workspace = domain.create_workspace("Aurora")
    goal = domain.create_goal(CreateGoalCommand(workspace.id, "<script>alert(1)</script>", ("x",)))
    assert group.connection.execute("SELECT count(*) FROM schema_migrations").fetchone() == (3,)
    catalog = SqliteInspectionCatalog(group)
    assert catalog.records(workspace.id, "goals")[0].id == str(goal.id)
    assert "<script>" in dict(catalog.records(workspace.id, "goals")[0].fields)["objective"]
    modes = SqliteOperationalStore(group)
    modes.restrict(workspace.id, OperationalMode.RESTORE_QUARANTINE, "operator-1", clock.now())
    with pytest.raises(InvariantViolation, match="operational_mode_blocks"), group.runtime.atomic():
        group.runtime.require_consequential_dispatch(workspace.id)
    group.close()
    reopened = SqliteStoreGroup(path)
    try:
        assert (
            SqliteOperationalStore(reopened).mode(workspace.id)
            is OperationalMode.RESTORE_QUARANTINE
        )
        assert len(reopened.connection.execute("SELECT * FROM operational_audit").fetchall()) == 1
        with pytest.raises(InvariantViolation, match="operational_release_not_supported"):
            SqliteOperationalStore(reopened).restrict(
                workspace.id, OperationalMode.NORMAL, "operator-1", clock.now()
            )
    finally:
        reopened.close()


def test_authenticated_fresh_restore_quarantines_old_approval_state(tmp_path: Path) -> None:
    source, identity = tmp_path / "canonical.sqlite", tmp_path / "identity.sqlite"
    migrate_database(source)
    migrate_operator_database(identity)
    group, operator_store = SqliteStoreGroup(source), SqliteOperatorStore(identity)
    clock = FakeClock(datetime(2026, 9, 21, tzinfo=UTC))
    domain = DomainService(group.domain, clock, DeterministicIdGenerator("backup"))
    workspace = domain.create_workspace("Aurora Desk")
    operators = OperatorService(operator_store, group.domain, clock, TestSecrets())
    credential = operators.provision_local(workspace.id, OperatorId("admin"), OperatorRole.ADMIN)
    session = operators.login(credential.value).value
    adapter = SqliteBackupAdapter(source, tmp_path / "backups", tmp_path / "restores")
    backup = BackupService(operators, adapter)
    try:
        manifest = backup.create(session, workspace.id, "before-revocation")
        assert len(manifest.sha256) == 64
        OperationalModeService(operators, SqliteOperationalStore(group)).restrict(
            session, workspace.id, OperationalMode.MAINTENANCE
        )
        backup.restore(session, workspace.id, "before-revocation", "drill-1")
        restored_path = tmp_path / "restores" / "drill-1" / "canonical.sqlite"
        restored = SqliteStoreGroup(restored_path)
        try:
            assert (
                SqliteOperationalStore(restored).mode(workspace.id)
                is OperationalMode.RESTORE_QUARANTINE
            )
            with (
                pytest.raises(InvariantViolation, match="operational_mode_blocks"),
                restored.runtime.atomic(),
            ):
                restored.runtime.require_consequential_dispatch(workspace.id)
        finally:
            restored.close()
        with pytest.raises(InvariantViolation, match="invalid_backup_name"):
            backup.restore(session, workspace.id, "../identity.sqlite", "drill-2")
    finally:
        operator_store.close()
        group.close()
