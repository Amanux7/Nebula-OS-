# mypy: disable-error-code="no-untyped-call,no-untyped-def"
"""Cross-stage service contracts and snapshots exercised against SQLite."""

import asyncio
import importlib
from typing import Any

import pytest

from agent_company_os.adapters.agent_selector import DeterministicAgentSelector
from agent_company_os.adapters.fake_model import FakeModel
from agent_company_os.adapters.ids import DeterministicIdGenerator
from agent_company_os.adapters.orchestration_strategy import FakeOrchestrationStrategy
from agent_company_os.adapters.result_aggregator import DeterministicResultAggregator
from agent_company_os.adapters.sqlite_database import migrate_database
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.application.orchestration import OrchestrationService
from agent_company_os.application.organization import AgentRegistry
from agent_company_os.application.runtime import AgentRuntimeService
from agent_company_os.application.service import DomainService
from agent_company_os.domain.agent import Fact, SuppliedContext
from test_communication import complete, decision
from test_organization import OrgHarness


def wire_test_stores(monkeypatch, graph):
    for name in ("test_organization", "test_communication", "test_memory", "test_knowledge"):
        module = importlib.import_module(name)
        for constructor, store in (
            ("InMemoryRuntimeStore", graph.runtime),
            ("InMemoryKnowledgeStore", graph.knowledge),
            ("InMemoryMemoryStore", graph.memory),
            ("InMemoryOrganizationStore", graph.organization),
            ("InMemoryOrchestrationStore", graph.orchestration),
            ("InMemoryCommunicationStore", graph.communication),
        ):
            if hasattr(module, constructor):
                monkeypatch.setattr(module, constructor, lambda *args, selected=store: selected)


@pytest.mark.parametrize(
    "module,function,required",
    [
        ("test_memory", "test_episodic_candidate_review_promotion_and_retrieval", "memory_packs"),
        ("test_memory", "test_supersession_is_atomic_and_preserves_history", "entries"),
        ("test_knowledge", "test_history_eviction_and_disable", "evidence"),
        ("test_organization", "test_org_orchestration_end_to_end", "delegation_attempts"),
        ("test_organization", "test_message_and_handoff_use_pinned_graph", "handoffs"),
    ],
)
def test_canonical_subsystem_reopen(tmp_path, clock, monkeypatch, module, function, required):
    path = tmp_path / "subsystems.sqlite"
    migrate_database(path)
    graph = SqliteStoreGroup(path)
    wire_test_stores(monkeypatch, graph)
    service = DomainService(graph.domain, clock, DeterministicIdGenerator())
    getattr(importlib.import_module(module), function)(service, clock)
    before = graph.connection.execute(
        "SELECT * FROM canonical_records ORDER BY collection,record_key"
    ).fetchall()
    assert any(row[0] == required for row in before)
    graph.close()
    monkeypatch.undo()
    del graph, service
    reopened = SqliteStoreGroup(path)
    assert (
        reopened.connection.execute(
            "SELECT * FROM canonical_records ORDER BY collection,record_key"
        ).fetchall()
        == before
    )
    for event in reopened.domain.events():
        assert reopened.domain.get_workspace(event.workspace_id).id == event.workspace_id
    reopened.close()


@pytest.mark.parametrize("subsystem", ["knowledge", "memory"])
def test_retrieval_services_reconstructed_from_canonical_state(
    tmp_path, clock, monkeypatch, subsystem
):
    from agent_company_os.adapters.knowledge_ingestion import TextKnowledgeIngestor
    from agent_company_os.adapters.lexical_memory import LexicalMemoryRetriever
    from agent_company_os.adapters.lexical_retrieval import LexicalKnowledgeRetriever
    from agent_company_os.application.knowledge import KnowledgeService
    from agent_company_os.application.memory import MemoryService
    from agent_company_os.domain.knowledge import KnowledgeQuery
    from agent_company_os.domain.memory import MemoryQuery
    from test_knowledge import setup
    from test_memory import SCOPE, setup_memory

    path = tmp_path / "retrieve.sqlite"
    migrate_database(path)
    graph = SqliteStoreGroup(path)
    wire_test_stores(monkeypatch, graph)
    domain = DomainService(graph.domain, clock, DeterministicIdGenerator())
    harness: Any
    service: Any
    pack: Any
    if subsystem == "memory":
        harness = setup_memory(domain, clock)
        harness.approve(harness.propose())
        before_pack = harness.retrieve()
    else:
        harness = setup(domain, clock)
        before_pack = harness.retrieve()
    before_run = harness.current()
    graph.close()
    monkeypatch.undo()
    del graph, harness, domain
    graph = SqliteStoreGroup(path)
    assert graph.runtime.get_run(before_run.workspace_id, before_run.id) == before_run
    ids = DeterministicIdGenerator("retrieval-restarted")
    if subsystem == "memory":
        service = MemoryService(graph.memory, LexicalMemoryRetriever(), clock, ids)
        pack = service.retrieve(
            before_run.workspace_id,
            before_run.id,
            before_run.version,
            MemoryQuery(before_run.workspace_id, "Paper Kite", "pricing preference", (SCOPE,)),
        )
        assert pack.result.hits == before_pack.result.hits
    else:
        service = KnowledgeService(
            graph.knowledge, TextKnowledgeIngestor(), LexicalKnowledgeRetriever(), clock, ids
        )
        pack = service.retrieve(
            before_run.workspace_id,
            before_run.id,
            before_run.version,
            KnowledgeQuery(before_run.workspace_id, "pricing"),
        )
        assert pack.result == before_pack.result
    graph.close()


def test_multidepartment_wait_resume_after_reopen(tmp_path, clock, monkeypatch):
    path = tmp_path / "orchestration.sqlite"
    migrate_database(path)
    graph = SqliteStoreGroup(path)
    wire_test_stores(monkeypatch, graph)
    h = OrgHarness(DomainService(graph.domain, clock, DeterministicIdGenerator()), clock)
    ws, orchestration_id = h.workspace.id, h.run.id
    for index in range(2):
        current = graph.orchestration.run(ws, orchestration_id)
        task = h.materialization.tasks[index]
        delegated = h.orchestration.delegate(ws, current.id, task.task_id, current.version)
        assert delegated is not None
        context = SuppliedContext(
            ws, task.task_id, ("fact",), (Fact("fact", "verified", "caller"),)
        )
        h.runtime.model = FakeModel(
            (
                complete()
                if index == 0
                else decision("request_more_context", {"missing_fields": ["fact"]}),
            )
        )
        result = asyncio.run(
            h.orchestration.execute(ws, current.id, delegated.id, current.version, context)
        )
    assert result.status.value == "waiting"
    completed = graph.runtime.runs(ws)[0]
    h.publish_next()
    before = graph.orchestration.run(ws, orchestration_id)
    plans = graph.orchestration.plans(ws, orchestration_id)
    delegations = graph.orchestration.delegations(ws, orchestration_id)
    materialization = h.materialization
    assert delegated is not None
    waiting_id, delegation_id = result.id, delegated.id
    graph.close()
    monkeypatch.undo()
    del graph, h
    graph = SqliteStoreGroup(path)
    ids = DeterministicIdGenerator("restart")
    runtime = AgentRuntimeService(graph.runtime, clock, ids, FakeModel((complete(), complete())))
    registry = AgentRegistry(graph.organization, clock)
    strategy = FakeOrchestrationStrategy(())  # Any unrequested replan must fail.
    orchestration = OrchestrationService(
        graph.orchestration,
        strategy,
        DeterministicAgentSelector(graph.runtime),
        DeterministicResultAggregator(),
        runtime,
        clock,
        ids,
        registry,
    )
    assert graph.orchestration.run(ws, orchestration_id) == before
    assert graph.orchestration.plans(ws, orchestration_id) == plans
    assert graph.orchestration.delegations(ws, orchestration_id) == delegations
    assert before.organization is not None
    assert before.organization.graph.version.value == 1
    assert registry.capture(ws).graph.version.value == 2
    assert graph.runtime.get_run(ws, waiting_id) == result
    resumed = asyncio.run(
        orchestration.resume_delegation(
            ws, orchestration_id, delegation_id, before.version, context
        )
    )
    assert resumed.deadline == result.deadline
    assert resumed.working_state.iteration > result.working_state.iteration
    assert graph.runtime.get_run(ws, completed.id) == completed
    current = graph.orchestration.run(ws, orchestration_id)
    last = materialization.tasks[2]
    delegated = orchestration.delegate(ws, current.id, last.task_id, current.version)
    assert delegated is not None
    asyncio.run(
        orchestration.execute(
            ws,
            current.id,
            delegated.id,
            current.version,
            SuppliedContext(ws, last.task_id, ("fact",), (Fact("fact", "verified", "caller"),)),
        )
    )
    final = graph.orchestration.run(ws, orchestration_id)
    assert final.status.value == "completed"
    assert final.agent_run_count == 3
    assert graph.domain.get_goal(before.goal_id).status.value == "satisfied"
    from agent_company_os.application.audit import AuditQueryService

    audit = AuditQueryService(graph.runtime, orchestration=graph.orchestration)
    timeline = audit.timeline_for_goal(ws, before.goal_id)
    assert any(e.subject_type == "orchestration_plan" for e in timeline)
    assert any(e.subject_type == "delegation" for e in timeline)
    assert timeline == audit.timeline_for_goal(ws, before.goal_id)
    graph.close()


@pytest.mark.parametrize("failed", [False, True])
def test_child_result_crash_reconciles_once_after_reopen(tmp_path, clock, monkeypatch, failed):
    from test_recovery import ProcessDeath

    path = tmp_path / "child-recovery.sqlite"
    migrate_database(path)
    graph = SqliteStoreGroup(path)
    wire_test_stores(monkeypatch, graph)
    h = OrgHarness(DomainService(graph.domain, clock, DeterministicIdGenerator()), clock)
    ws, parent_id = h.workspace.id, h.run.id
    current = graph.orchestration.run(ws, parent_id)
    task_id = h.materialization.tasks[0].task_id
    delegation = h.orchestration.delegate(ws, parent_id, task_id, current.version)
    assert delegation is not None
    h.runtime.model = FakeModel(("invalid-json" if failed else complete(),))

    def die(*args):
        raise ProcessDeath()

    monkeypatch.setattr(h.orchestration, "_reconcile_result", die)
    with pytest.raises(ProcessDeath):
        asyncio.run(
            h.orchestration.execute(
                ws,
                parent_id,
                delegation.id,
                current.version,
                SuppliedContext(ws, task_id, ("fact",), (Fact("fact", "verified", "caller"),)),
            )
        )
    child = graph.runtime.runs(ws)[0]
    assert child.status.value == ("failed" if failed else "succeeded")
    assert graph.orchestration.run(ws, parent_id).failed_attempt_count == 0
    graph.close()
    monkeypatch.undo()
    del graph, h
    graph = SqliteStoreGroup(path)
    ids = DeterministicIdGenerator("child-recovery")
    runtime = AgentRuntimeService(graph.runtime, clock, ids, FakeModel(()))
    orchestration = OrchestrationService(
        graph.orchestration,
        FakeOrchestrationStrategy(()),
        DeterministicAgentSelector(graph.runtime),
        DeterministicResultAggregator(),
        runtime,
        clock,
        ids,
        AgentRegistry(graph.organization, clock),
    )
    parent = graph.orchestration.run(ws, parent_id)
    assert orchestration.reconcile_child(ws, parent_id, child.id, parent.version) == child
    repaired = graph.orchestration.run(ws, parent_id)
    assert repaired.failed_attempt_count == int(failed)
    assert repaired.agent_run_count == parent.agent_run_count == 1
    events = graph.orchestration.events(ws)
    orchestration.reconcile_child(ws, parent_id, child.id, repaired.version)
    assert graph.orchestration.run(ws, parent_id) == repaired
    assert graph.orchestration.events(ws) == events
    graph.close()
