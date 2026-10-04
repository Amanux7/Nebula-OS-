# mypy: disable-error-code="no-untyped-call,no-untyped-def"
"""Stage 11 release acceptance against genuinely restored canonical state."""

import asyncio
import json
import os
import sqlite3
from threading import Event as ThreadEvent
from threading import Thread
from time import perf_counter

import pytest

from agent_company_os.adapters.ids import DeterministicIdGenerator
from agent_company_os.adapters.operational_store import SqliteOperationalStore
from agent_company_os.adapters.operator_store import SqliteOperatorStore, migrate_operator_database
from agent_company_os.adapters.sqlite_backup import SqliteBackupAdapter
from agent_company_os.adapters.sqlite_inspection import SqliteInspectionCatalog
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.application.audit import AuditQueryService
from agent_company_os.application.operations import OperationalModeService
from agent_company_os.application.operator import OperatorService
from agent_company_os.application.operator_queries import OperatorQueryService
from agent_company_os.application.recovery import RecoveryService
from agent_company_os.application.tool_runtime import ToolRuntimeService
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.governance import DecisionKind
from agent_company_os.domain.operations import OperationalMode
from agent_company_os.domain.operator import OperatorId, OperatorRole
from agent_company_os.operator_host import HostConfig, create_server
from test_operator import TestSecrets
from test_operator_http import login, request
from test_recovery import ProcessDeath, prepare, reopen


def operator_service(tmp_path, group, clock, recovery):
    path = tmp_path / "identity.sqlite"
    migrate_operator_database(path)
    identity = SqliteOperatorStore(path)
    operators = OperatorService(identity, group.domain, clock, TestSecrets())
    ws = group.domain.workspaces()[0].id
    admin = operators.provision_local(ws, OperatorId("restore-admin"), OperatorRole.ADMIN)
    viewer = operators.provision_local(ws, OperatorId("restore-viewer"), OperatorRole.VIEWER)
    return (
        identity,
        operators,
        OperationalModeService(operators, SqliteOperationalStore(group), recovery),
        admin,
        viewer,
    )


def test_stale_approval_remains_blocked_after_authenticated_release(tmp_path, clock, monkeypatch):
    path, remote, graph, executor, h = prepare(tmp_path, clock, monkeypatch)
    ws, tool, intent, run_id = h.workspace.id, h.tool, h.record().intent, h.run.id
    backup = SqliteBackupAdapter(path, tmp_path / "backups", tmp_path / "restores")
    backup.create("approved", ws, clock.now())
    h.governance.decide(ws, intent.id, intent.fingerprint, h.reviewer, DecisionKind.REVOKED)
    graph.close()
    executor.close()
    monkeypatch.undo()
    backup.restore("approved", "old", ws, "local-admin", clock.now())
    restored = tmp_path / "restores/old/canonical.sqlite"
    graph, executor, recovery, runtime = reopen(restored, remote, clock, tool)
    identity, operators, modes, admin, viewer = operator_service(tmp_path, graph, clock, recovery)
    try:
        token = operators.login(admin.value).value
        viewer_token = operators.login(viewer.value).value
        denied = modes.release(viewer_token, ws)
        assert not denied.success and denied.reason == "admin_required"
        assert modes.status(token, ws) is OperationalMode.RESTORE_QUARANTINE
        context = modes.context(token, ws)
        assert (
            context
            and context.backup_id == "approved"
            and str(intent.id) in context.held_intent_ids
        )
        assert modes.release(token, ws).success
        assert executor.effect_count() == 0
        run = graph.runtime.get_run(ws, run_id)
        with pytest.raises(InvariantViolation, match="restored_intent_requires_new_work"):
            asyncio.run(runtime.resume_approval(ws, run.id, intent.id, run.version))
        assert executor.effect_count() == 0
        assert [a.success for a in modes.audit(token, ws)] == [True, False]
        assert not modes.release(token, ws).success
    finally:
        identity.close()
        graph.close()
        executor.close()
    graph = SqliteStoreGroup(restored)
    try:
        assert graph.runtime.operational_mode(ws) is OperationalMode.NORMAL
        assert graph.runtime.intent_held(ws, intent.id)
    finally:
        graph.close()


@pytest.mark.parametrize("unknown", [False, True])
def test_remote_effect_after_snapshot_reconcile_then_release(tmp_path, clock, monkeypatch, unknown):
    path, remote, graph, executor, h = prepare(tmp_path, clock, monkeypatch)
    ws, tool, intent, run_id = h.workspace.id, h.tool, h.record().intent, h.run.id
    backup = SqliteBackupAdapter(path, tmp_path / "backups", tmp_path / "restores")
    original_execute = executor.execute

    async def snapshot_then_effect(request_data, invocation):
        # Invocation is committed; snapshot precedes the independent remote effect.
        backup.create("claimed", ws, clock.now())
        await original_execute(request_data, invocation)
        raise ProcessDeath()

    monkeypatch.setattr(executor, "execute", snapshot_then_effect)
    with pytest.raises(ProcessDeath):
        h.resume()
    graph.close()
    executor.close()
    monkeypatch.undo()
    del graph, executor, h
    backup.restore("claimed", "restored", ws, "admin", clock.now())
    restored = tmp_path / "restores/restored/canonical.sqlite"
    graph, executor, recovery, runtime = reopen(restored, remote, clock, tool, unknown)
    identity, operators, modes, admin, _viewer = operator_service(tmp_path, graph, clock, recovery)
    try:
        invocation = graph.runtime.tool_invocations(ws, run_id)[0]
        outcome = asyncio.run(recovery.reconcile(ws, run_id, invocation.id, executor))
        assert outcome.outcome == ("outcome_unknown" if unknown else "observed_success")
        assert executor.calls == 0 and executor.effect_count() == 1
        token = operators.login(admin.value).value
        release = modes.release(token, ws)
        assert release.success and release.held_intent_count == 1
        assert executor.calls == 0
        assert graph.domain.get_goal(intent.goal_id).status.value == "active"
        action = graph.runtime.action(ws, intent.action_id)
        with pytest.raises(InvariantViolation):
            asyncio.run(
                runtime.tools.invoke(ws, run_id, action, graph.runtime.get_run(ws, run_id).version)
            )
        assert executor.effect_count() == 1
        if not unknown:
            assert len(graph.runtime.tool_receipts(ws, run_id)) == 1
            assert graph.runtime.governed_action(ws, intent.id).consumed
    finally:
        identity.close()
        graph.close()
        executor.close()


def test_release_audit_failure_rolls_back_mode(tmp_path, clock, monkeypatch):
    path, remote, graph, executor, h = prepare(tmp_path, clock, monkeypatch)
    ws, tool = h.workspace.id, h.tool
    backup = SqliteBackupAdapter(path, tmp_path / "backups", tmp_path / "restores")
    backup.create("snapshot", ws, clock.now())
    graph.close()
    executor.close()
    monkeypatch.undo()
    backup.restore("snapshot", "restored", ws, "admin", clock.now())
    graph, executor, recovery, _runtime = reopen(
        tmp_path / "restores/restored/canonical.sqlite", remote, clock, tool
    )
    identity, operators, modes, admin, _viewer = operator_service(tmp_path, graph, clock, recovery)
    try:
        token = operators.login(admin.value).value
        graph.connection.execute(
            "CREATE TRIGGER fail_release BEFORE INSERT ON quarantine_release_audit "
            "BEGIN SELECT RAISE(ABORT,'injected'); END"
        )
        with pytest.raises(sqlite3.IntegrityError):
            modes.release(token, ws)
        assert modes.status(token, ws) is OperationalMode.RESTORE_QUARANTINE
        graph.connection.execute("DROP TRIGGER fail_release")
        monkeypatch.setattr(
            recovery, "classify", lambda ws: (_ for _ in ()).throw(InvariantViolation("injected"))
        )
        assert modes.release(token, ws).reason == "classification_failed"
        assert modes.audit(token, ws)[0].reason == "classification_failed"
    finally:
        identity.close()
        graph.close()
        executor.close()


@pytest.mark.parametrize("damage", ["json", "digest", "schema", "corrupt"])
def test_restore_rejects_damaged_snapshot(tmp_path, clock, monkeypatch, damage):
    path, _remote, graph, executor, h = prepare(tmp_path, clock, monkeypatch)
    ws = h.workspace.id
    backup = SqliteBackupAdapter(path, tmp_path / "backups", tmp_path / "restores")
    backup.create("snapshot", ws, clock.now())
    graph.close()
    executor.close()
    manifest = tmp_path / "backups/snapshot/manifest.json"
    database = tmp_path / "backups/snapshot/canonical.sqlite"
    data = json.loads(manifest.read_text())
    if damage == "json":
        manifest.write_text("{broken")
    elif damage == "digest":
        data["sha256"] = "0" * 64
        manifest.write_text(json.dumps(data))
    else:
        connection = sqlite3.connect(database)
        if damage == "schema":
            connection.execute("INSERT INTO schema_migrations VALUES(999,'bad')")
        else:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("UPDATE canonical_records SET payload='{}' WHERE collection='runs'")
        connection.commit()
        connection.close()
        from hashlib import sha256

        data["sha256"] = sha256(database.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(data))
    with pytest.raises((InvariantViolation, sqlite3.Error)):
        backup.restore("snapshot", "rejected", ws, "admin", clock.now())
    assert not (tmp_path / "restores/rejected").exists()


def test_restore_paths_cleanup_permissions(tmp_path, clock, monkeypatch):
    path, _remote, graph, executor, h = prepare(tmp_path, clock, monkeypatch)
    ws = h.workspace.id
    backups, restores = tmp_path / "backups", tmp_path / "restores"
    backup = SqliteBackupAdapter(path, backups, restores)
    backup.create("snapshot", ws, clock.now())
    graph.close()
    executor.close()
    for name in ("../escape", "..", "absolute/file", "a\\b"):
        with pytest.raises(InvariantViolation):
            backup.restore("snapshot", name, ws, "admin", clock.now())
    with pytest.raises(InvariantViolation):
        SqliteBackupAdapter(path, backups, backups)
    backup.restore("snapshot", "once", ws, "admin", clock.now())
    before = (restores / "once/canonical.sqlite").read_bytes()
    with pytest.raises(FileExistsError):
        backup.restore("snapshot", "once", ws, "admin", clock.now())
    assert (restores / "once/canonical.sqlite").read_bytes() == before
    source_as_destination = SqliteBackupAdapter(path, backups, path.parent.parent)
    with pytest.raises(FileExistsError):
        source_as_destination.restore("snapshot", path.parent.name, ws, "admin", clock.now())
    original = backup._scope

    def fail_staging(path, workspace):
        if path.name == "restore.incomplete":
            raise InvariantViolation("injected_restore_failure")
        original(path, workspace)

    monkeypatch.setattr(backup, "_scope", fail_staging)
    with pytest.raises(InvariantViolation, match="injected_restore_failure"):
        backup.restore("snapshot", "partial", ws, "admin", clock.now())
    assert not (restores / "partial").exists()
    if os.name != "nt":
        assert (backups / "snapshot").stat().st_mode & 0o077 == 0
        assert (backups / "snapshot/canonical.sqlite").stat().st_mode & 0o077 == 0
    else:
        # chmod on Windows does not create a private ACL; check only the promised behavior.
        assert (backups / "snapshot/canonical.sqlite").is_file()


def test_restored_http_host_inspection_release_and_readiness(tmp_path, clock, monkeypatch):
    path, remote, graph, executor, h = prepare(tmp_path, clock, monkeypatch)
    ws, tool = h.workspace.id, h.tool
    identity, operators, _modes, admin, _viewer = operator_service(tmp_path, graph, clock, None)
    identity.close()
    backup = SqliteBackupAdapter(path, tmp_path / "backups", tmp_path / "restores")
    backup.create("before", ws, clock.now())
    graph.close()
    executor.close()

    monkeypatch.undo()
    backup.restore("before", "host", ws, "admin", clock.now())
    restored = tmp_path / "restores/host/canonical.sqlite"
    server = create_server(HostConfig(restored, tmp_path / "identity.sqlite"))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_port
        cookie = login(port, admin.value)
        context = json.loads(request(port, "GET", "/api/v1/restore", cookie=cookie)[2])
        assert context["context"]["backup_id"] == "before"
        assert request(port, "GET", "/health/ready")[0] == 200
        assert (
            json.loads(request(port, "GET", "/api/v1/status", cookie=cookie)[2])["mode"]
            == "restore_quarantine"
        )
        cases = json.loads(request(port, "GET", "/api/v1/recovery", cookie=cookie)[2])
        assert cases["items"] and cases["items"][0]["explanation"]
        status, _, result = request(
            port, "POST", "/api/v1/mode/release", {}, cookie, f"http://127.0.0.1:{port}"
        )
        assert status == 200 and json.loads(result)["success"]
        diag = json.loads(request(port, "GET", "/api/v1/diagnostics", cookie=cookie)[2])
        assert diag["startup"]["canonical_schema"] == 4
        assert diag["requests"]["requests"] > 0
        identity = sqlite3.connect(tmp_path / "identity.sqlite")
        identity.execute("PRAGMA ignore_check_constraints=ON")
        identity.execute("UPDATE operator_schema SET version=999")
        identity.commit()
        identity.close()
        assert request(port, "GET", "/health/live")[0] == 200
        assert request(port, "GET", "/health/ready")[0] != 200
    finally:
        server.shutdown()
        thread.join(5)
        server.server_close()
    graph, executor, _recovery, _runtime = reopen(restored, remote, clock, tool)
    assert executor.effect_count() == 0 and graph.runtime.tool_invocations(ws, h.run.id) == ()
    graph.close()
    executor.close()


def test_backup_partial_cleanup_and_link_guard(tmp_path, clock, monkeypatch):
    path, _remote, graph, executor, h = prepare(tmp_path, clock, monkeypatch)
    ws = h.workspace.id
    adapter = SqliteBackupAdapter(path, tmp_path / "backups", tmp_path / "restores")
    graph.close()
    executor.close()
    original_scope = adapter._scope

    def fail_snapshot(selected, workspace):
        if selected != path:
            raise InvariantViolation("injected_snapshot_failure")
        original_scope(selected, workspace)

    monkeypatch.setattr(adapter, "_scope", fail_snapshot)
    with pytest.raises(InvariantViolation, match="injected_snapshot_failure"):
        adapter.create("partial", ws, clock.now())
    assert not (tmp_path / "backups/partial").exists()
    # Deterministically exercise Windows reparse-point rejection even where the
    # test principal lacks symlink creation privileges.
    from pathlib import Path

    monkeypatch.setattr(Path, "is_junction", lambda p: p == tmp_path / "junction")
    with pytest.raises(InvariantViolation, match="backup_path_escape"):
        SqliteBackupAdapter(path, tmp_path / "junction", tmp_path / "restores")


def test_receipt_event_reader_sees_one_committed_snapshot(tmp_path, clock, monkeypatch):
    path, _remote, graph, executor, h = prepare(tmp_path, clock, monkeypatch)
    ws, run_id, goal_id = h.workspace.id, h.run.id, h.run.goal_id
    identity, operators, _modes, admin, _viewer = operator_service(tmp_path, graph, clock, None)
    token = operators.login(admin.value).value
    identity.close()
    started, done = ThreadEvent(), ThreadEvent()
    observed: list[tuple[int, int, float]] = []
    errors: list[BaseException] = []
    threads: list[Thread] = []

    def read_snapshot():
        started.set()
        began = perf_counter()
        try:
            reader = SqliteStoreGroup(path)
            accounts = SqliteOperatorStore(tmp_path / "identity.sqlite")
            try:
                service = OperatorService(accounts, reader.domain, clock, TestSecrets())
                ids = DeterministicIdGenerator("reader")
                tools = ToolRuntimeService(reader.runtime, reader.registry, clock, ids)
                queries = OperatorQueryService(
                    service,
                    reader.runtime,
                    AuditQueryService(reader.runtime),
                    RecoveryService(reader.runtime, tools, clock, ids),
                    SqliteInspectionCatalog(reader),
                )
                with accounts.atomic(), reader.transaction():
                    receipts = queries.inspect(token, ws, "receipts").items
                    events = queries.goal_timeline(token, ws, goal_id, limit=100).items
                observed.append(
                    (
                        len(receipts),
                        sum(e.event_kind == "tool_receipt_recorded" for e in events),
                        perf_counter() - began,
                    )
                )
            finally:
                accounts.close()
                reader.close()
        except BaseException as error:
            errors.append(error)
        finally:
            done.set()

    def pause_at_receipt_commit(point):
        if point == "before_commit" and graph.runtime._tool_receipts and not threads:
            worker = Thread(target=read_snapshot)
            threads.append(worker)
            worker.start()
            assert started.wait(5)
            assert not done.wait(0.1)  # no half-committed receipt or event visible

    graph.fault = pause_at_receipt_commit
    try:
        h.resume()
        assert done.wait(10)
        assert not errors
        assert observed[0][:2] == (1, 1)
        assert observed[0][2] < 10
        assert len(graph.runtime.tool_receipts(ws, run_id)) == 1
    finally:
        for worker in threads:
            worker.join(10)
        graph.close()
        executor.close()


def test_competing_release_has_one_winner(tmp_path, clock, monkeypatch):
    path, _remote, graph, executor, h = prepare(tmp_path, clock, monkeypatch)
    ws = h.workspace.id
    backup = SqliteBackupAdapter(path, tmp_path / "backups", tmp_path / "restores")
    backup.create("snapshot", ws, clock.now())
    graph.close()
    executor.close()
    backup.restore("snapshot", "competing", ws, "admin", clock.now())
    restored = tmp_path / "restores/competing/canonical.sqlite"
    outcomes: list[bool] = []
    errors: list[BaseException] = []

    def release():
        try:
            group = SqliteStoreGroup(restored)
            try:
                result = SqliteOperationalStore(group).release(
                    ws, "trusted-test-admin", clock.now(), lambda: (), True
                )
                outcomes.append(result.success)
            finally:
                group.close()
        except BaseException as error:
            errors.append(error)

    workers = [Thread(target=release), Thread(target=release)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(10)
        assert not worker.is_alive()
    assert not errors and sorted(outcomes) == [False, True]
    group = SqliteStoreGroup(restored)
    try:
        assert len(SqliteOperationalStore(group).release_audit(ws)) == 2
    finally:
        group.close()
