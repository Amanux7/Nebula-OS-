# mypy: disable-error-code="no-untyped-call,no-untyped-def"
"""Canonical services operate against genuinely reopened SQLite adapters."""

from pathlib import Path

import pytest

from agent_company_os.adapters.ids import DeterministicIdGenerator
from agent_company_os.adapters.sqlite_database import migrate_database
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.application.service import CreateGoalCommand, DomainService
from agent_company_os.domain.errors import VersionConflict
from agent_company_os.domain.governance import DecisionKind
from test_governance import GovernanceHarness


def test_domain_reopen_and_stale_version(tmp_path, clock):
    path = tmp_path / "domain.sqlite"
    migrate_database(path)
    graph = SqliteStoreGroup(path)
    service = DomainService(graph.domain, clock, DeterministicIdGenerator())
    workspace = service.create_workspace("Durable company")
    goal = service.create_goal(CreateGoalCommand(workspace.id, "Outcome", ("Evidence",)))
    graph.close()
    del graph, service
    first = SqliteStoreGroup(path)
    second = SqliteStoreGroup(path)
    assert first.domain.get_goal(goal.id) == goal
    assert second.domain.get_goal(goal.id) == goal
    service = DomainService(first.domain, clock, DeterministicIdGenerator("worker-a"))
    service.activate_goal(goal.id, goal.version)
    other = DomainService(second.domain, clock, DeterministicIdGenerator("worker-b"))
    with pytest.raises(VersionConflict):
        other.activate_goal(goal.id, goal.version)
    first.close()
    second.close()


@pytest.mark.parametrize(
    "decision", [None, DecisionKind.APPROVED, DecisionKind.REJECTED, DecisionKind.REVOKED]
)
def test_governance_true_reopen(tmp_path, clock, monkeypatch, decision):
    path = tmp_path / "runtime.sqlite"
    migrate_database(path)
    graph = SqliteStoreGroup(path)
    monkeypatch.setattr("test_governance.InMemoryRuntimeStore", lambda domain: graph.runtime)
    domain = DomainService(graph.domain, clock, DeterministicIdGenerator())
    harness = GovernanceHarness(domain, clock)
    harness.drive()
    if decision is DecisionKind.REVOKED:
        harness.review()
    if decision is not None:
        harness.review(decision)
    before = harness.record()
    run = graph.runtime.get_run(harness.workspace.id, harness.run.id)
    graph.close()
    del harness, domain, graph
    reopened = SqliteStoreGroup(path)
    assert reopened.runtime.governed_action(run.workspace_id, before.intent.id) == before
    assert reopened.runtime.get_run(run.workspace_id, run.id) == run
    reopened.close()


def test_receipt_consumption_reopen(tmp_path, clock, monkeypatch):
    path = tmp_path / "receipts.sqlite"
    migrate_database(path)
    graph = SqliteStoreGroup(path)
    monkeypatch.setattr("test_governance.InMemoryRuntimeStore", lambda domain: graph.runtime)
    harness = GovernanceHarness(
        DomainService(graph.domain, clock, DeterministicIdGenerator()), clock
    )
    harness.drive()
    harness.review()
    harness.resume()
    record, receipts, run = harness.record(), harness.receipts(), harness.run
    graph.close()
    del harness, graph
    reopened = SqliteStoreGroup(path)
    assert reopened.runtime.governed_action(run.workspace_id, record.intent.id).consumed
    assert reopened.runtime.tool_receipts(run.workspace_id, run.id) == receipts
    assert reopened.runtime.get_run(run.workspace_id, run.id) == run
    reopened.close()


@pytest.mark.parametrize("phase", ["state_write", "audit_write", "before_commit"])
def test_atomic_state_audit_rollback(tmp_path: Path, clock, phase):
    path = tmp_path / "rollback.sqlite"
    migrate_database(path)
    graph = SqliteStoreGroup(path)
    service = DomainService(graph.domain, clock, DeterministicIdGenerator())

    def fail(point):
        if point == phase:
            raise OSError("fixture disk failure")

    graph.fault = fail
    with pytest.raises(OSError):
        service.create_workspace("Must roll back")
    graph.close()
    reopened = SqliteStoreGroup(path)
    assert reopened.domain.events() == ()
    assert reopened.connection.execute("SELECT count(*) FROM domain_records").fetchone() == (0,)
    reopened.close()
