# mypy: disable-error-code="no-untyped-call,no-untyped-def"
"""Real connection teardown with an independent remote fixture ledger."""

import asyncio
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from agent_company_os.adapters.fake_model import FakeModel
from agent_company_os.adapters.ids import DeterministicIdGenerator
from agent_company_os.adapters.recoverable_fixture import (
    RecoverableFixtureExecutor,
    bootstrap_fixture,
)
from agent_company_os.adapters.sqlite_database import migrate_database
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.application.governance import GovernanceService
from agent_company_os.application.recovery import RecoveryService
from agent_company_os.application.runtime import AgentRuntimeService
from agent_company_os.application.service import DomainService
from agent_company_os.application.tool_runtime import ToolRuntimeService
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.recovery import RecoveryReason
from agent_company_os.domain.tools import ToolFailure, ToolReceipt
from test_governance import GovernanceHarness
from test_tools import complete


class ProcessDeath(BaseException):
    pass


def prepare(tmp_path, clock, monkeypatch):
    path, remote_path = tmp_path / "app.sqlite", tmp_path / "remote.sqlite"
    migrate_database(path)
    bootstrap_fixture(remote_path)
    graph = SqliteStoreGroup(path)
    executor = RecoverableFixtureExecutor(remote_path)
    monkeypatch.setattr("test_governance.InMemoryRuntimeStore", lambda domain: graph.runtime)
    monkeypatch.setattr("test_governance.ToolRegistry", lambda: graph.registry)
    harness = GovernanceHarness(
        DomainService(graph.domain, clock, DeterministicIdGenerator()), clock, executor=executor
    )
    harness.drive()
    harness.review()
    return path, remote_path, graph, executor, harness


def reopen(path, remote_path, clock, tool, unknown=False, namespace="recovery"):
    graph = SqliteStoreGroup(path)
    executor = RecoverableFixtureExecutor(remote_path, unknown=unknown)
    graph.registry.bind(tool.grant, executor)
    ids = DeterministicIdGenerator(namespace)
    governance = GovernanceService(graph.runtime, clock, ids)
    tools = ToolRuntimeService(graph.runtime, graph.registry, clock, ids, governance)
    recovery = RecoveryService(graph.runtime, tools, clock, ids)
    runtime = AgentRuntimeService(
        graph.runtime, clock, ids, FakeModel((complete("approved_001"),)), tools
    )
    return graph, executor, recovery, runtime


@pytest.mark.parametrize("window", ["before_claim", "after_claim", "after_effect", "after_receipt"])
@pytest.mark.parametrize("unknown", [False, True])
def test_crash_windows_genuine_reopen(tmp_path, clock, monkeypatch, window, unknown):
    path, remote_path, graph, executor, h = prepare(tmp_path, clock, monkeypatch)
    ws, run_id, tool, intent_id = h.workspace.id, h.run.id, h.tool, h.record().intent.id
    original_deadline, original_iteration = h.run.deadline, h.run.working_state.iteration
    original_execute = executor.execute

    async def dying_execute(request, invocation, selected=h, execute=original_execute):
        # A separate connection sees the committed claim before external executor entry.
        observer = SqliteStoreGroup(path)
        assert len(observer.runtime.tool_invocations(ws, run_id)) == 1
        observer.close()
        assert not graph.connection.in_transaction
        if window == "after_claim":
            raise ProcessDeath()
        result = await execute(request, invocation)
        if window == "after_effect":
            raise ProcessDeath()
        if window == "after_receipt":
            from agent_company_os.application.tool_validation import input_json, validate_output

            with graph.runtime.atomic():
                graph.runtime.finish_tool_invocation(
                    ToolReceipt(
                        selected.domain.ids.tool_receipt_id(),
                        invocation.finish(clock.now(), None),
                        validate_output(result, tool, request),
                        len(input_json(request).encode()),
                        len(result.encode()),
                        "observed",
                    )
                )
            raise ProcessDeath()
        return result

    monkeypatch.setattr(executor, "execute", dying_execute)
    if window == "before_claim":

        def crash(point):
            if point == "before_commit" and graph.runtime._tool_invocations:
                raise ProcessDeath()

        graph.fault = crash
    with pytest.raises(ProcessDeath):
        h.resume()
    graph.close()
    executor.close()
    monkeypatch.undo()
    # Discard all service/executor instances, not just a connection inside a live harness.
    del h, graph, executor, original_execute, dying_execute
    graph, executor, recovery, runtime = reopen(path, remote_path, clock, tool, unknown)
    run = graph.runtime.get_run(ws, run_id)
    assert run.deadline == original_deadline
    assert run.working_state.iteration == original_iteration
    if window == "before_claim":
        assert graph.runtime.tool_invocations(ws, run_id) == ()
        assert executor.effect_count() == 0
        assert graph.runtime.governed_action(ws, intent_id).decisions[-1].kind.value == "approved"
        # The claim rollback leaves a running claimed model iteration, not an approval wait.
        action = graph.runtime.action(
            ws, graph.runtime.governed_action(ws, intent_id).intent.action_id
        )
        result = asyncio.run(runtime.tools.invoke(ws, run_id, action, run.version))
        assert executor.effect_count() == 1
        assert result.deadline == original_deadline
    else:
        invocation = graph.runtime.tool_invocations(ws, run_id)[0]
        result = asyncio.run(recovery.reconcile(ws, run_id, invocation.id, executor))
        assert executor.calls == 0
        if window == "after_claim":
            assert result.reason is (
                RecoveryReason.MANUAL_REVIEW if unknown else RecoveryReason.SAFE_TO_RETRY
            )
            assert executor.effect_count() == 0
        elif unknown and window != "after_receipt":
            assert result.outcome == "outcome_unknown"
            assert graph.domain.get_task(run.task_id).status.value != "completed"
            assert graph.domain.get_goal(run.goal_id).status.value == "active"
        else:
            assert result.outcome == "observed_success"
            assert graph.runtime.governed_action(ws, intent_id).consumed
            current = graph.runtime.get_run(ws, run_id)
            before = graph.runtime.events(ws)
            asyncio.run(recovery.reconcile(ws, run_id, invocation.id, executor))
            assert graph.runtime.events(ws) == before
            finished = asyncio.run(runtime.drive(ws, run_id, current.version))
            assert finished.status.value == "succeeded"
            assert graph.domain.get_task(run.task_id).status.value == "completed"
            assert executor.effect_count() == 1
        with pytest.raises(InvariantViolation):
            action = graph.runtime.action(ws, invocation.action_id)
            asyncio.run(
                runtime.tools.invoke(ws, run_id, action, graph.runtime.get_run(ws, run_id).version)
            )
    graph.close()
    executor.close()


def test_expiry_and_disable_survive_restart(tmp_path, clock, monkeypatch):
    path, remote_path, graph, executor, h = prepare(tmp_path, clock, monkeypatch)
    ws, run_id, tool, intent = h.workspace.id, h.run.id, h.tool, h.record().intent
    graph.registry.set_enabled(ws, tool.definition.id, False)
    graph.close()
    executor.close()
    monkeypatch.undo()
    del graph, executor, h
    clock.advance(timedelta(minutes=5))
    graph, executor, recovery, runtime = reopen(path, remote_path, clock, tool)
    assert any(c.reason is RecoveryReason.EXPIRED for c in recovery.classify(ws))
    with pytest.raises(ToolFailure):
        graph.registry.resolve(ws, tool.grant)
    with pytest.raises((InvariantViolation, ToolFailure)):
        asyncio.run(
            runtime.resume_approval(
                ws, run_id, intent.id, graph.runtime.get_run(ws, run_id).version
            )
        )
    assert executor.effect_count() == 0
    graph.close()
    executor.close()


def test_real_process_death_after_remote_commit(tmp_path, clock, monkeypatch):
    path, remote, graph, executor, h = prepare(tmp_path, clock, monkeypatch)
    ws, run_id, tool = h.workspace.id, h.run.id, h.tool
    intent, version = h.record().intent.id, h.run.version
    graph.close()
    executor.close()
    monkeypatch.undo()
    del graph, executor, h
    worker = Path(__file__).parent / "fixtures/recovery_crash_worker.py"
    process = subprocess.run(
        [
            sys.executable,
            str(worker),
            str(path),
            str(remote),
            clock.now().isoformat(),
            str(ws),
            str(run_id),
            str(intent),
            str(version.value),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert process.returncode == 73, process.stderr
    graph, executor, recovery, runtime = reopen(path, remote, clock, tool)
    assert executor.effect_count() == 1
    assert graph.runtime.tool_receipts(ws, run_id) == ()
    invocation = graph.runtime.tool_invocations(ws, run_id)[0]
    outcome = asyncio.run(recovery.reconcile(ws, run_id, invocation.id, executor))
    assert outcome.outcome == "observed_success"
    assert executor.calls == 0
    assert graph.runtime.governed_action(ws, intent).consumed
    assert not graph.runtime.get_run(ws, run_id).working_state.invocation_pending
    metrics = recovery.reliability_snapshot(ws)
    assert metrics["recovery_cases_total"] == 1
    assert metrics["reconciliation_success"] == 1
    assert metrics["unknown_outcomes"] == 0
    from agent_company_os.application.audit import AuditQueryService

    run = graph.runtime.get_run(ws, run_id)
    timeline = AuditQueryService(graph.runtime).timeline_for_goal(ws, run.goal_id)
    assert {
        "recovery_detected",
        "recovery_lookup",
        "recovery_receipt_reconciled",
        "recovery_parent_reconciled",
    } <= {event.event_kind for event in timeline}
    graph.close()
    executor.close()


def test_read_only_recovery_retry_eligibility_is_not_dispatch_authority(
    tmp_path, clock, monkeypatch
):
    from agent_company_os.adapters.tool_executors import CompanyFactLookup
    from test_tools import FACT, call, setup

    path = tmp_path / "reads.sqlite"
    migrate_database(path)
    graph = SqliteStoreGroup(path)
    monkeypatch.setattr("test_tools.InMemoryRuntimeStore", lambda domain, s=graph.runtime: s)
    monkeypatch.setattr("test_tools.ToolRegistry", lambda s=graph.registry: s)

    class CrashedRead:
        async def execute(self, request, invocation):
            raise ProcessDeath()

    harness = setup(
        DomainService(graph.domain, clock, DeterministicIdGenerator()),
        clock,
        (call(),),
        CrashedRead(),
    )
    ws, run_id, tool = harness.run.workspace_id, harness.run.id, harness.company
    with pytest.raises(ProcessDeath):
        harness.drive()
    graph.close()
    monkeypatch.undo()
    del graph, harness
    graph = SqliteStoreGroup(path)
    graph.registry.bind(tool.grant, CompanyFactLookup({"Acme": (FACT,)}))
    ids = DeterministicIdGenerator("read-recovery")
    tools = ToolRuntimeService(graph.runtime, graph.registry, clock, ids)
    recovery = RecoveryService(graph.runtime, tools, clock, ids)
    cases = recovery.classify(ws)
    assert any(
        c.subject_type == "tool_invocation" and c.reason is RecoveryReason.SAFE_TO_RETRY
        for c in cases
    )
    assert graph.runtime.tool_receipts(ws, run_id) == ()
    # A classification is not a command to reset the existing one-way claim or its budget.
    invocation = graph.runtime.tool_invocations(ws, run_id)[0]
    run = graph.runtime.get_run(ws, run_id)
    with pytest.raises(InvariantViolation):
        asyncio.run(
            tools.invoke(ws, run_id, graph.runtime.action(ws, invocation.action_id), run.version)
        )
    assert graph.runtime.get_run(ws, run_id) == run
    graph.close()


def test_unknown_receipt_and_consumption_survive_reopen(tmp_path, clock, monkeypatch):
    path, remote_path, graph, executor, h = prepare(tmp_path, clock, monkeypatch)
    ws, run_id, tool, intent = h.workspace.id, h.run.id, h.tool, h.record().intent.id
    original = executor.execute

    async def timeout_after_write(request, invocation, dispatch=original):
        await dispatch(request, invocation)
        raise TimeoutError("response lost")

    monkeypatch.setattr(executor, "execute", timeout_after_write)
    asyncio.run(h.tools.resume_intent(ws, run_id, intent, h.run.version))
    receipts = graph.runtime.tool_receipts(ws, run_id)
    assert receipts[0].remote_outcome == "unknown"
    graph.close()
    executor.close()
    monkeypatch.undo()
    del graph, executor, h, original, timeout_after_write
    graph, executor, recovery, runtime = reopen(path, remote_path, clock, tool)
    assert graph.runtime.tool_receipts(ws, run_id) == receipts
    assert graph.runtime.governed_action(ws, intent).consumed
    assert any(case.reason is RecoveryReason.TERMINAL_UNKNOWN for case in recovery.classify(ws))
    result = asyncio.run(recovery.reconcile(ws, run_id, receipts[0].invocation.id, executor))
    assert result.reason is RecoveryReason.TERMINAL_UNKNOWN
    assert graph.runtime.tool_receipts(ws, run_id) == receipts
    assert executor.calls == 0 and executor.effect_count() == 1
    graph.close()
    executor.close()
