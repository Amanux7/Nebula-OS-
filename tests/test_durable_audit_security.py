# mypy: disable-error-code="no-untyped-call,no-untyped-def"
"""Durable audit, corruption rejection, and independent-worker contention."""

import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from agent_company_os.adapters.ids import DeterministicIdGenerator
from agent_company_os.adapters.sqlite_database import migrate_database
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.application.audit import AuditQueryService
from agent_company_os.application.service import DomainService
from agent_company_os.domain.errors import DomainError, InvariantViolation, WorkspaceMismatch
from test_recovery import prepare, reopen


def test_audit_queries_reopen_order_lineage_and_redaction(tmp_path, clock, monkeypatch):
    path, remote, graph, executor, h = prepare(tmp_path, clock, monkeypatch)
    h.resume()
    ws, run, intent = h.workspace.id, h.run, h.record().intent
    service = AuditQueryService(graph.runtime)
    before = service.timeline_for_goal(ws, run.goal_id)
    assert before == tuple(sorted(before, key=lambda e: (e.timestamp, str(e.event_id))))
    assert service.timeline_for_task(ws, run.task_id)
    assert service.timeline_for_agent_run(ws, run.id)
    assert service.timeline_for_action_intent(ws, intent.id)
    assert service.approvals_for_task(ws, run.task_id)[0].consumed
    assert service.tool_invocations_for_execution(ws, run.execution_id)[0].receipt_id
    trace = service.trace_goal(ws, run.goal_id)
    assert trace[0].action_intent_id == str(intent.id)
    assert trace[0].receipt_id
    # Exact protected action payload must not be duplicated into timeline projections.
    assert not any(
        key in {"message", "payload", "reason", "body", "arguments"}
        for event in before
        for key, _ in event.metadata
    )
    message = json.loads(intent.arguments_json)["message"]
    assert message not in repr(before)
    assert message not in repr(graph.runtime.events(ws))
    foreign = DomainService(graph.domain, clock, DeterministicIdGenerator("foreign"))
    other = foreign.create_workspace("Other company")
    for query, subject in (
        (service.timeline_for_goal, run.goal_id),
        (service.timeline_for_task, run.task_id),
        (service.timeline_for_agent_run, run.id),
        (service.timeline_for_action_intent, intent.id),
        (service.approvals_for_task, run.task_id),
        (service.tool_invocations_for_execution, run.execution_id),
        (service.trace_goal, run.goal_id),
    ):
        with pytest.raises(WorkspaceMismatch):
            query(other.id, subject)
    graph.close()
    executor.close()
    monkeypatch.undo()
    del graph, executor, h, service, foreign
    reopened = SqliteStoreGroup(path)
    audit = AuditQueryService(reopened.runtime)
    assert audit.timeline_for_goal(ws, run.goal_id) == before
    assert audit.trace_goal(ws, run.goal_id) == trace
    reopened.close()


def test_two_workers_resume_claim_and_consume_once(tmp_path, clock, monkeypatch):
    path, remote, graph, executor, h = prepare(tmp_path, clock, monkeypatch)
    ws, run_id, tool = h.workspace.id, h.run.id, h.tool
    record, version = h.record(), h.run.version
    graph.close()
    executor.close()
    monkeypatch.undo()
    del graph, executor, h
    barrier = Barrier(2)

    def worker():
        current, connector, recovery, runtime = reopen(path, remote, clock, tool)
        try:
            barrier.wait(timeout=20)
            try:
                asyncio.run(runtime.resume_approval(ws, run_id, record.intent.id, version))
                return "won"
            except DomainError:
                return "lost"
        finally:
            current.close()
            connector.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert sorted(results) == ["lost", "won"]
    current, connector, recovery, runtime = reopen(path, remote, clock, tool)
    assert connector.effect_count() == 1
    assert len(current.runtime.tool_invocations(ws, run_id)) == 1
    assert len(current.runtime.tool_receipts(ws, run_id)) == 1
    assert current.runtime.governed_action(ws, record.intent.id).consumed
    current.close()
    connector.close()


@pytest.mark.parametrize(
    "corruption", ["key", "enum", "missing", "json", "type", "schema", "impossible", "workspace"]
)
def test_corrupt_runtime_rejected_on_open(tmp_path, clock, monkeypatch, corruption):
    path, remote, graph, executor, h = prepare(tmp_path, clock, monkeypatch)
    graph.close()
    executor.close()
    monkeypatch.undo()
    del graph, executor, h
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA ignore_check_constraints=ON")
    if corruption in {"enum", "missing", "json"}:
        payload = json.loads(
            connection.execute(
                "SELECT payload FROM canonical_records WHERE collection='runs'"
            ).fetchone()[0]
        )
        if corruption == "enum":
            payload["status"] = "invented"
        elif corruption == "missing":
            del payload["deadline"]
        connection.execute(
            "UPDATE canonical_records SET payload=? WHERE collection='runs'",
            ("{" if corruption == "json" else json.dumps(payload),),
        )
    elif corruption == "impossible":
        payload = json.loads(
            connection.execute(
                "SELECT payload FROM canonical_records WHERE collection='governance'"
            ).fetchone()[0]
        )
        payload["consumed"] = True
        connection.execute(
            "UPDATE canonical_records SET payload=? WHERE collection='governance'",
            (json.dumps(payload),),
        )
    else:
        column, value = {
            "key": ("record_key", '{"value":"forged"}'),
            "type": ("collection", "executable_python"),
            "schema": ("schema_version", 99),
            "workspace": ("workspace_id", "foreign-workspace"),
        }[corruption]
        # Column names come from this fixed test allowlist, never query input.
        connection.execute(
            f"UPDATE canonical_records SET {column}=? WHERE collection='runs'", (value,)
        )
    connection.commit()
    connection.close()
    with pytest.raises(InvariantViolation):
        SqliteStoreGroup(path)


def test_nested_transaction_rollback_preserves_outer_work(tmp_path, clock):
    path = tmp_path / "nested.sqlite"
    migrate_database(path)
    graph = SqliteStoreGroup(path)
    domain = DomainService(graph.domain, clock, DeterministicIdGenerator())
    with graph.runtime.atomic():
        outer = domain.create_workspace("Keep")
        with pytest.raises(ValueError), graph.runtime.atomic():
            domain.create_workspace("Rollback")
            raise ValueError("nested failure")
    graph.close()
    reopened = SqliteStoreGroup(path)
    assert len(reopened.domain.events()) == 1
    assert reopened.domain.get_workspace(outer.id) == outer
    reopened.close()
