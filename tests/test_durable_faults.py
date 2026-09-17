# mypy: disable-error-code="no-untyped-call,no-untyped-def"
"""Faults never turn an ambiguous dispatch into reusable authorization."""

import asyncio
from contextlib import suppress
from datetime import timedelta

import pytest

from agent_company_os.adapters import sqlite_database
from agent_company_os.adapters.recoverable_fixture import (
    RecoverableFixtureExecutor,
    bootstrap_fixture,
)
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.recovery import RemoteStatus, execution_key
from agent_company_os.domain.tools import FixtureMessageInput, ToolFailure
from test_recovery import ProcessDeath, prepare, reopen


def test_migration_sequence_requires_explicit_upgrade(tmp_path, monkeypatch):
    path = tmp_path / "upgrade.sqlite"
    scripts = sqlite_database._migrations()
    monkeypatch.setattr(sqlite_database, "_migrations", lambda: scripts[:1])
    sqlite_database.migrate_database(path)
    monkeypatch.undo()
    with pytest.raises(InvariantViolation):
        sqlite_database.open_database(path)
    sqlite_database.migrate_database(path)
    sqlite_database.migrate_database(path)
    graph = SqliteStoreGroup(path)
    assert graph.connection.execute("SELECT count(*) FROM schema_migrations").fetchone() == (2,)
    graph.close()


def test_independent_fixture_idempotency_and_status(tmp_path):
    path = tmp_path / "remote.sqlite"
    bootstrap_fixture(path)
    remote = RecoverableFixtureExecutor(path)
    request = FixtureMessageInput("customer:paper-kite", "Bounded test message")
    assert asyncio.run(remote.lookup_status("key")).status is RemoteStatus.NEVER_RECEIVED
    output = remote.dispatch("key", request)
    remote.close()
    remote = RecoverableFixtureExecutor(path)
    assert remote.dispatch("key", request) == output
    assert remote.effect_count() == 1
    assert asyncio.run(remote.lookup_status("key")).status is RemoteStatus.PROCESSED_SUCCESS
    with pytest.raises(InvariantViolation):
        remote.dispatch("key", FixtureMessageInput(request.destination, "Changed payload"))
    remote.reject = True
    with pytest.raises(ToolFailure):
        remote.dispatch("failed", request)
    assert asyncio.run(remote.lookup_status("failed")).status is RemoteStatus.PROCESSED_FAILURE
    remote.unknown = True
    assert asyncio.run(remote.lookup_status("key")).status is RemoteStatus.UNKNOWN
    remote.close()


@pytest.mark.parametrize("fault", ["state_write", "audit_write", "before_commit"])
@pytest.mark.parametrize("remote_failure", [False, True])
def test_reconciliation_storage_failure_preserves_claim(
    tmp_path, clock, monkeypatch, fault, remote_failure
):
    path, remote_path, graph, remote, h = prepare(tmp_path, clock, monkeypatch)
    ws, run_id, tool = h.workspace.id, h.run.id, h.tool
    execute = remote.execute
    remote.reject = remote_failure

    async def die(request, invocation, dispatch=execute):
        with suppress(ToolFailure):
            await dispatch(request, invocation)
        raise ProcessDeath()

    monkeypatch.setattr(remote, "execute", die)
    with pytest.raises(ProcessDeath):
        h.resume()
    graph.close()
    remote.close()
    monkeypatch.undo()
    del graph, remote, h, die, execute
    graph, remote, recovery, runtime = reopen(path, remote_path, clock, tool)
    invocation = graph.runtime.tool_invocations(ws, run_id)[0]

    def disk_failure(phase):
        if phase == fault:
            raise OSError("fixture disk unavailable")

    graph.fault = disk_failure
    with pytest.raises(OSError):
        asyncio.run(recovery.reconcile(ws, run_id, invocation.id, remote))
    graph.close()
    remote.close()
    del graph, remote, recovery, runtime
    graph, remote, recovery, runtime = reopen(
        path, remote_path, clock, tool, namespace="recovery-second"
    )
    assert len(graph.runtime.tool_invocations(ws, run_id)) == 1
    assert graph.runtime.tool_receipts(ws, run_id) == ()
    assert asyncio.run(remote.lookup_status(execution_key(invocation))).status is (
        RemoteStatus.PROCESSED_FAILURE if remote_failure else RemoteStatus.PROCESSED_SUCCESS
    )
    outcome = asyncio.run(recovery.reconcile(ws, run_id, invocation.id, remote))
    assert outcome.outcome == ("observed_failure" if remote_failure else "observed_success")
    assert remote.calls == 0
    graph.close()
    remote.close()


@pytest.mark.parametrize("parent", ["execution", "deadline"])
def test_recovery_evidence_does_not_reopen_expired_or_cancelled_work(
    tmp_path, clock, monkeypatch, parent
):
    path, remote_path, graph, remote, h = prepare(tmp_path, clock, monkeypatch)
    ws, run_id, tool = h.workspace.id, h.run.id, h.tool
    execute = remote.execute

    async def die(request, invocation, dispatch=execute):
        await dispatch(request, invocation)
        raise ProcessDeath()

    monkeypatch.setattr(remote, "execute", die)
    with pytest.raises(ProcessDeath):
        h.resume()
    if parent == "execution":
        execution = graph.domain.get_execution(h.run.execution_id)
        h.domain.cancel_execution(execution.id, execution.version)
    else:
        clock.advance(timedelta(days=1))
    graph.close()
    remote.close()
    monkeypatch.undo()
    del graph, remote, h, die, execute
    graph, remote, recovery, runtime = reopen(path, remote_path, clock, tool)
    invocation = graph.runtime.tool_invocations(ws, run_id)[0]
    with suppress(InvariantViolation):
        asyncio.run(recovery.reconcile(ws, run_id, invocation.id, remote))
    assert graph.runtime.tool_receipts(ws, run_id)[0].remote_outcome == "observed"
    run = graph.runtime.get_run(ws, run_id)
    assert run.working_state.invocation_pending
    assert graph.domain.get_goal(run.goal_id).status.value == "active"
    assert remote.calls == 0
    graph.close()
    remote.close()
