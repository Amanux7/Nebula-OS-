"""Canonical spatial relationships and protected-content projection boundaries."""

import asyncio
from dataclasses import replace
from pathlib import Path

from agent_company_os.adapters.agent_selector import DeterministicAgentSelector
from agent_company_os.adapters.clocks import SystemClock
from agent_company_os.adapters.fake_model import FakeModel
from agent_company_os.adapters.ids import DeterministicIdGenerator
from agent_company_os.adapters.knowledge_ingestion import TextKnowledgeIngestor
from agent_company_os.adapters.lexical_memory import LexicalMemoryRetriever
from agent_company_os.adapters.lexical_retrieval import LexicalKnowledgeRetriever
from agent_company_os.adapters.orchestration_strategy import FakeOrchestrationStrategy
from agent_company_os.adapters.result_aggregator import DeterministicResultAggregator
from agent_company_os.adapters.sqlite_database import migrate_database
from agent_company_os.adapters.sqlite_inspection import SqliteInspectionCatalog
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.application.knowledge import KnowledgeService, PublishKnowledgeSource
from agent_company_os.application.memory import MemoryService
from agent_company_os.application.orchestration import OrchestrationService
from agent_company_os.application.runtime import AgentRuntimeService
from agent_company_os.application.service import (
    CreateExecutionCommand,
    CreateGoalCommand,
    CreateTaskAttemptCommand,
    CreateTaskCommand,
    DomainService,
)
from agent_company_os.domain.agent import SuppliedContext
from agent_company_os.domain.ids import Version
from agent_company_os.domain.knowledge import KnowledgeQuery, KnowledgeScope, SourceType, TrustClass
from agent_company_os.domain.memory import MemoryAccessPolicy, MemoryQuery
from agent_company_os.domain.orchestration import PlannedTask, PlanProposal
from agent_company_os.operator_cli import seed_aurora

PRIVATE = "private-evidence-sentence-unique"


def test_membership_and_review_metadata_survive_reopen_without_memory_content(
    tmp_path: Path,
) -> None:
    path = tmp_path / "spatial.sqlite"
    migrate_database(path)
    workspace = seed_aurora(path, inspection_marker=PRIVATE)
    group = SqliteStoreGroup(path)
    try:
        catalog = SqliteInspectionCatalog(group)
        graph = group.organization.version(workspace, Version(1))
        for kind in ("organization", "graph_versions"):
            row = catalog.records(workspace, kind)[0]
            fields = dict(row.fields)
            assert fields["membership_count"] == "3"
            for i, membership in enumerate(graph.memberships):
                assert fields[f"membership.{i}.agent_definition_id"] == str(membership.agent_id)
                assert fields[f"membership.{i}.department_id"] == str(membership.department_id)
                assert fields[f"membership.{i}.status"] == membership.status.value
                assert any(
                    link.kind == "agents" and link.id == str(membership.agent_id)
                    for link in row.links
                )
        entry = group.memory.entries(workspace)[0]
        memory_row = catalog.records(workspace, "memory")[0]
        fields = dict(memory_row.fields)
        assert fields["memory_type"] == entry.memory_type.value
        assert fields["scope.kind"] == entry.scope.kind.value
        assert (
            fields["candidate.provenance.authority"] == entry.candidate.provenance.authority.value
        )
        assert fields["candidate.provenance.run_id"] == str(entry.candidate.provenance.run_id)
        assert fields["reviewed_by"] == entry.reviewed_by
        assert fields["reviewed_at"] == entry.reviewed_at.isoformat()
        assert fields["provenance.reference_count"] == "1"
        assert PRIVATE not in repr(memory_row)
        assert not {"subject", "content", "scope.key", "claim_key", "claim_value"} & fields.keys()
        before = memory_row
    finally:
        group.close()
    reopened = SqliteStoreGroup(path)
    try:
        assert SqliteInspectionCatalog(reopened).records(workspace, "memory")[0] == before
    finally:
        reopened.close()


def test_task_edges_come_from_materialized_plan_identifiers(tmp_path: Path) -> None:
    path = tmp_path / "dependencies.sqlite"
    migrate_database(path)
    workspace = seed_aurora(path)
    group = SqliteStoreGroup(path)
    clock, ids = SystemClock(), DeterministicIdGenerator("spatial-dependency")
    try:
        domain = DomainService(group.domain, clock, ids)
        goal = domain.create_goal(CreateGoalCommand(workspace, "Dependency test", ("Reviewed",)))
        goal = domain.activate_goal(goal.id, goal.version)
        tasks = (
            PlannedTask("source", "Duplicate title", ("Reviewed",)),
            PlannedTask("dependent", "Duplicate title", ("Reviewed",), ("source",)),
        )
        service = OrchestrationService(
            group.orchestration,
            FakeOrchestrationStrategy((PlanProposal(workspace, goal.id, tasks),)),
            DeterministicAgentSelector(group.runtime),
            DeterministicResultAggregator(),
            AgentRuntimeService(group.runtime, clock, ids, FakeModel(())),
            clock,
            ids,
        )
        run = asyncio.run(service.start(workspace, goal.id))
        materialization = service.materialize(workspace, run.id, run.version)
        identity = {t.planned_task_id: str(t.task_id) for t in materialization.tasks}
        group.close()
        group = SqliteStoreGroup(path)
        rows = {r.id: r for r in SqliteInspectionCatalog(group).records(workspace, "tasks")}
        dependency = rows[identity["dependent"]]
        fields = dict(dependency.fields)
        assert fields["dependency.0.task_id"] == identity["source"]
        assert fields["dependency_count"] == "1"
        assert fields["plan_id"] == str(materialization.plan_id)
        assert fields["plan_version"] == str(materialization.plan_version.value)
        assert any(
            link.kind == "tasks" and link.id == identity["source"] for link in dependency.links
        )
        assert dict(rows[identity["source"]].fields)["dependency_count"] == "0"
    finally:
        group.close()


def test_run_pack_metadata_uses_exact_evidence_and_memory_ids_without_payloads(
    tmp_path: Path,
) -> None:
    path = tmp_path / "evidence.sqlite"
    migrate_database(path)
    workspace = seed_aurora(path, inspection_marker=PRIVATE)
    group = SqliteStoreGroup(path)
    clock, ids = SystemClock(), DeterministicIdGenerator("spatial-evidence")
    try:
        knowledge = KnowledgeService(
            group.knowledge, TextKnowledgeIngestor(), LexicalKnowledgeRetriever(), clock, ids
        )
        source = knowledge.publish_source(
            PublishKnowledgeSource(
                workspace,
                "Approved evidence",
                SourceType.TEXT,
                TrustClass.APPROVED_INTERNAL,
                PRIVATE.encode(),
            )
        )
        entry = group.memory.entries(workspace)[0]
        definition = group.runtime.definitions(workspace)[0]
        definition = replace(
            definition,
            version=definition.version.next(),
            knowledge_scope=KnowledgeScope((source.id,)),
            memory_access=MemoryAccessPolicy((entry.scope,)),
        )
        group.runtime.publish(definition)
        domain = DomainService(group.domain, clock, ids)
        goal = domain.create_goal(CreateGoalCommand(workspace, "Pack metadata test", ("Reviewed",)))
        goal = domain.activate_goal(goal.id, goal.version)
        task = domain.create_task(
            CreateTaskCommand(workspace, goal.id, "Inspect evidence", ("Reviewed",))
        )
        task = domain.ready_task(task.id, task.version)
        task = domain.start_task(task.id, task.version)
        execution = domain.create_execution(
            CreateExecutionCommand(workspace, goal.id, "fixture", 2)
        )
        execution = domain.start_execution(execution.id, execution.version)
        attempt = domain.create_task_attempt(
            CreateTaskAttemptCommand(workspace, task.id, execution.id)
        )
        attempt = domain.start_task_attempt(attempt.id, attempt.version)
        run = AgentRuntimeService(group.runtime, clock, ids, FakeModel(())).start(
            workspace,
            definition.definition.id,
            definition.version,
            attempt.id,
            SuppliedContext(workspace, task.id, ("Reviewed",), ()),
        )
        evidence = knowledge.retrieve(
            workspace, run.id, run.version, KnowledgeQuery(workspace, PRIVATE)
        )
        run = group.runtime.get_run(workspace, run.id)
        memory = MemoryService(group.memory, LexicalMemoryRetriever(), clock, ids)
        memory_pack = memory.retrieve(
            workspace,
            run.id,
            run.version,
            MemoryQuery(workspace, entry.subject, PRIVATE, (entry.scope,)),
        )
        assert evidence.result.candidates and memory_pack.result.hits
        group.close()
        group = SqliteStoreGroup(path)
        catalog = SqliteInspectionCatalog(group)
        row = next(r for r in catalog.records(workspace, "runs") if r.id == str(run.id))
        fields = dict(row.fields)
        candidate = evidence.result.candidates[0]
        assert fields["evidence.0.pack_id"] == str(evidence.id)
        assert fields["evidence.0.source.0.source_id"] == str(source.id)
        assert fields["evidence.0.source.0.source_version"] == "1"
        assert fields["evidence.0.source.0.chunk_id"] == str(candidate.chunk.id)
        assert fields["memory_pack.0.id"] == str(memory_pack.id)
        assert fields["memory_pack.0.entry.0.id"] == str(entry.id)
        assert PRIVATE not in repr(row)
        version = next(
            r for r in catalog.records(workspace, "knowledge_versions") if r.id == f"{source.id}:1"
        )
        assert dict(version.fields)["chunk.0.id"] == str(candidate.chunk.id)
        assert PRIVATE not in repr(version)
    finally:
        group.close()
