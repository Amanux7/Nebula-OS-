"""Stage 11 durable safety controls on genuinely reopened SQLite stores."""

import asyncio
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
from agent_company_os.domain.governance import DecisionKind
from agent_company_os.domain.operations import OperationalMode
from agent_company_os.domain.operator import OperatorId, OperatorRole
from test_operator import TestSecrets
from test_recovery import prepare, reopen


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


def test_backup_rejects_multi_workspace_source_without_plaintext_output(tmp_path: Path) -> None:
    source = tmp_path / "canonical.sqlite"
    migrate_database(source)
    group = SqliteStoreGroup(source)
    clock = FakeClock(datetime(2026, 9, 21, tzinfo=UTC))
    domain = DomainService(group.domain, clock, DeterministicIdGenerator("scope"))
    workspace = domain.create_workspace("Authorized")
    domain.create_workspace("Unrelated")
    group.close()
    backup_root = tmp_path / "backups"
    adapter = SqliteBackupAdapter(source, backup_root, tmp_path / "restores")
    with pytest.raises(InvariantViolation, match="backup_requires_single_authorized_workspace"):
        adapter.create("scoped", workspace.id, clock.now())
    assert not (backup_root / "scoped").exists()


def test_stale_approved_snapshot_cannot_duplicate_remote_effect(
    tmp_path: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, remote, group, executor, harness = prepare(  # type: ignore[no-untyped-call]
        tmp_path, clock, monkeypatch
    )
    workspace, run_id, intent_id = harness.workspace.id, harness.run.id, harness.record().intent.id
    adapter = SqliteBackupAdapter(path, tmp_path / "backups", tmp_path / "restores")
    adapter.create("approved", workspace, clock.now())
    harness.resume()
    assert executor.effect_count() == 1
    group.close()
    executor.close()
    monkeypatch.undo()
    adapter.restore("approved", "stale", workspace, "operator", clock.now())
    restored_path = tmp_path / "restores" / "stale" / "canonical.sqlite"
    restored, remote_executor, _recovery, runtime = reopen(  # type: ignore[no-untyped-call]
        restored_path, remote, clock, harness.tool
    )
    try:
        old = restored.runtime.get_run(workspace, run_id)
        assert (
            restored.runtime.governed_action(workspace, intent_id).decisions[-1].kind.value
            == "approved"
        )
        cases = _recovery.classify(workspace)
        assert any(
            case.subject_type == "action_intent" and case.reason.value == "manual_review_required"
            for case in cases
        )
        with pytest.raises(InvariantViolation, match="operational_mode_blocks"):
            asyncio.run(runtime.resume_approval(workspace, run_id, intent_id, old.version))
        assert remote_executor.effect_count() == 1
        assert remote_executor.calls == 0
        assert restored.runtime.tool_invocations(workspace, run_id) == ()
    finally:
        remote_executor.close()
        restored.close()


def test_revocation_after_backup_does_not_survive_as_dispatch_authority(
    tmp_path: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, remote, group, executor, harness = prepare(  # type: ignore[no-untyped-call]
        tmp_path, clock, monkeypatch
    )
    workspace, intent_id = harness.workspace.id, harness.record().intent.id
    adapter = SqliteBackupAdapter(path, tmp_path / "backups", tmp_path / "restores")
    adapter.create("approved", workspace, clock.now())
    harness.governance.decide(
        workspace,
        intent_id,
        harness.record().intent.fingerprint,
        harness.reviewer,
        DecisionKind.REVOKED,
    )
    assert harness.record().decisions[-1].kind is DecisionKind.REVOKED
    group.close()
    executor.close()
    monkeypatch.undo()
    adapter.restore("approved", "old-approval", workspace, "operator", clock.now())
    restored_path = tmp_path / "restores" / "old-approval" / "canonical.sqlite"
    restored, remote_executor, recovery, runtime = reopen(  # type: ignore[no-untyped-call]
        restored_path, remote, clock, harness.tool
    )
    try:
        assert (
            restored.runtime.governed_action(workspace, intent_id).decisions[-1].kind
            is DecisionKind.APPROVED
        )
        assert any(
            case.reason.value == "manual_review_required" for case in recovery.classify(workspace)
        )
        old = restored.runtime.get_run(workspace, harness.run.id)
        with pytest.raises(InvariantViolation, match="operational_mode_blocks"):
            asyncio.run(runtime.resume_approval(workspace, old.id, intent_id, old.version))
        assert remote_executor.effect_count() == 0
    finally:
        remote_executor.close()
        restored.close()
