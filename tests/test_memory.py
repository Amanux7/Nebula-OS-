# mypy: disable-error-code="no-untyped-def"
"""Governed-memory lifecycle, isolation, poisoning and runtime tests."""

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_company_os.adapters.clocks import FakeClock
from agent_company_os.adapters.fake_model import FakeModel
from agent_company_os.adapters.in_memory import InMemoryDomainStore
from agent_company_os.adapters.lexical_memory import LexicalMemoryRetriever
from agent_company_os.adapters.memory_store import InMemoryMemoryStore
from agent_company_os.adapters.runtime_store import InMemoryRuntimeStore
from agent_company_os.application.memory import MemoryService, ProposeMemoryCandidate, with_memory
from agent_company_os.application.research_agent import research_brief_agent
from agent_company_os.application.runtime import AgentRuntimeService
from agent_company_os.application.runtime_serialization import serialize_run
from agent_company_os.application.service import (
    CreateExecutionCommand,
    CreateGoalCommand,
    CreateTaskAttemptCommand,
    CreateTaskCommand,
    DomainService,
)
from agent_company_os.domain.agent import (
    AgentDefinitionId,
    AgentRun,
    AgentRunId,
    Fact,
    SourceText,
    SuppliedContext,
)
from agent_company_os.domain.errors import (
    InvalidStateTransition,
    InvariantViolation,
    VersionConflict,
    WorkspaceMismatch,
)
from agent_company_os.domain.events import EventType
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.memory import (
    MemoryAccessPolicy,
    MemoryAuthority,
    MemoryCandidate,
    MemoryCandidateId,
    MemoryCandidateStatus,
    MemoryContextPack,
    MemoryEntryStatus,
    MemoryPolicy,
    MemoryPolicyDecision,
    MemoryProvenance,
    MemoryProvenanceKind,
    MemoryQuery,
    MemoryRetrievalResult,
    MemoryScope,
    MemoryScopeKind,
    MemorySensitivity,
    MemoryType,
    serialize_candidate,
    serialize_entry,
    serialize_memory_pack,
)

CASES = json.loads((Path(__file__).parent / "fixtures/agent_eval/memory_cases.json").read_text())[
    "cases"
]
SCOPE = MemoryScope(MemoryScopeKind.DOMAIN, "research")


def decision(kind: str, payload: object) -> str:
    return json.dumps({"schema_version": 1, "action_type": kind, "payload": payload})


def completion(fact: Fact) -> str:
    return decision(
        "complete_task",
        {
            "findings": [{"key": fact.key, "value": fact.value, "source_id": fact.source_id}],
            "gaps": [],
        },
    )


@dataclass
class MemoryHarness:
    service: DomainService
    runtime_store: InMemoryRuntimeStore
    memory_store: InMemoryMemoryStore
    memory: MemoryService
    clock: FakeClock
    source_run: AgentRun
    run: AgentRun

    def current(self) -> AgentRun:
        return self.runtime_store.get_run(self.run.workspace_id, self.run.id)

    def propose(
        self,
        *,
        content: str = "$49/month",
        kind: MemoryProvenanceKind = MemoryProvenanceKind.USER_STATEMENT,
        authority: MemoryAuthority = MemoryAuthority.STATED,
        memory_type: MemoryType = MemoryType.EPISODIC,
        sensitivity: MemorySensitivity = MemorySensitivity.NORMAL,
        source_references: tuple[str, ...] | None = None,
        expires_in: int | None = None,
        claim: bool = True,
    ) -> MemoryCandidate:
        source_id = {
            "$49/month": "caller",
            "$59/month": "price59",
            "password=supersecret": "secret",
            **{f"$4{index}/month": f"limit{index}" for index in range(6)},
        }.get(content, "caller")
        return self.memory.propose(
            ProposeMemoryCandidate(
                self.source_run.workspace_id,
                self.source_run.id,
                memory_type,
                "Paper Kite",
                content,
                SCOPE,
                MemoryProvenance(
                    kind, self.source_run.id, source_references or (source_id,), authority
                ),
                sensitivity,
                "pricing" if claim else None,
                content if claim else None,
                self.clock.now() + timedelta(seconds=expires_in) if expires_in else None,
            )
        )

    def approve(self, candidate: MemoryCandidate, *, supersedes=None):
        return self.memory.approve(
            candidate.workspace_id,
            candidate.id,
            candidate.version,
            "reviewer@example.test",
            supersedes_id=supersedes,
        )

    def retrieve(self, *, sensitivities=(MemorySensitivity.NORMAL,)) -> MemoryContextPack:
        run = self.current()
        return self.memory.retrieve(
            run.workspace_id,
            run.id,
            run.version,
            MemoryQuery(
                run.workspace_id, "Paper Kite", "pricing preference", (SCOPE,), sensitivities
            ),
        )


def _active_task(service: DomainService, workspace_id, goal_id, title: str):
    task = service.create_task(CreateTaskCommand(workspace_id, goal_id, title, ("Exact fact",)))
    task = service.ready_task(task.id, task.version)
    task = service.start_task(task.id, task.version)
    execution = service.create_execution(CreateExecutionCommand(workspace_id, goal_id, "test", 3))
    execution = service.start_execution(execution.id, execution.version)
    attempt = service.create_task_attempt(
        CreateTaskAttemptCommand(workspace_id, task.id, execution.id)
    )
    return task, service.start_task_attempt(attempt.id, attempt.version)


def setup_memory(
    service: DomainService, clock: FakeClock, *, sensitivities=(MemorySensitivity.NORMAL,)
) -> MemoryHarness:
    workspace = service.create_workspace("Memory Test Workspace")
    goal = service.create_goal(CreateGoalCommand(workspace.id, "Produce a brief", ("Grounded",)))
    goal = service.activate_goal(goal.id, goal.version)
    assert isinstance(service.store, InMemoryDomainStore)
    runtime_store = InMemoryRuntimeStore(service.store)
    definition = research_brief_agent(workspace.id, AgentDefinitionId("researcher"))
    runtime_store.publish(definition)
    task1, attempt1 = _active_task(service, workspace.id, goal.id, "Capture preference")
    source_context = SuppliedContext(
        workspace.id,
        task1.id,
        ("pricing",),
        (Fact("pricing", "$49/month", "caller"),),
        (
            SourceText("statement", "Paper Kite prefers monthly billing."),
            SourceText("price59", "$59/month"),
            SourceText("secret", "password=supersecret"),
            *(SourceText(f"limit{index}", f"$4{index}/month") for index in range(6)),
        ),
    )
    source_runtime = AgentRuntimeService(
        runtime_store, clock, service.ids, FakeModel((completion(source_context.facts[0]),))
    )
    source_run = source_runtime.start(
        workspace.id, definition.definition.id, definition.version, attempt1.id, source_context
    )
    source_run = asyncio.run(source_runtime.drive(workspace.id, source_run.id, source_run.version))
    access = MemoryAccessPolicy((SCOPE,), sensitivities)
    memory_definition = with_memory(definition, access)
    runtime_store.publish(memory_definition)
    task2, attempt2 = _active_task(service, workspace.id, goal.id, "Use preference")
    run_context = SuppliedContext(workspace.id, task2.id, ("pricing",), ())
    memory_store = InMemoryMemoryStore(runtime_store)
    memory = MemoryService(memory_store, LexicalMemoryRetriever(), clock, service.ids)
    runtime = AgentRuntimeService(runtime_store, clock, service.ids, FakeModel(()), memory=memory)
    run = runtime.start(
        workspace.id,
        memory_definition.definition.id,
        memory_definition.version,
        attempt2.id,
        run_context,
    )
    return MemoryHarness(service, runtime_store, memory_store, memory, clock, source_run, run)


def test_episodic_candidate_review_promotion_and_retrieval(service, clock) -> None:
    h = setup_memory(service, clock)
    candidate = h.propose()
    assert candidate.status is MemoryCandidateStatus.UNDER_REVIEW
    entry = h.approve(candidate)
    pack = h.retrieve()
    assert pack.result.hits[0].entry == entry
    assert "category=retained_memory" in serialize_memory_pack(pack)
    assert h.current().working_state.active_memory_pack_id == pack.id


def test_semantic_memory_always_requires_review(service, clock) -> None:
    h = setup_memory(service, clock)
    candidate = h.propose(memory_type=MemoryType.SEMANTIC)
    assert candidate.status is MemoryCandidateStatus.UNDER_REVIEW
    assert h.approve(candidate).memory_type is MemoryType.SEMANTIC


def test_model_generated_inference_is_rejected(service, clock) -> None:
    h = setup_memory(service, clock)
    candidate = h.propose(
        content="Paper Kite will churn",
        kind=MemoryProvenanceKind.AGENT_OUTPUT,
        authority=MemoryAuthority.INFERRED,
        source_references=(f"agent_run:{h.source_run.id}",),
        claim=False,
    )
    assert candidate.status is MemoryCandidateStatus.REJECTED
    with pytest.raises(InvalidStateTransition):
        h.approve(candidate)


def test_detectable_secret_is_rejected(service, clock) -> None:
    h = setup_memory(service, clock)
    candidate = h.propose(content="password=supersecret", claim=False)
    assert candidate.rejection_reason == "detectable_secret"


def test_official_knowledge_restatement_is_not_memory(service, clock) -> None:
    h = setup_memory(service, clock)

    class Knowledge:
        def active_pack(self, run):
            return None

        def evidence(self, run):
            return (Fact("pricing", "$49/month", "knowledge:official"),)

    h.memory.knowledge = Knowledge()
    candidate = h.propose(
        kind=MemoryProvenanceKind.KNOWLEDGE_EVIDENCE,
        authority=MemoryAuthority.OBSERVED,
        source_references=("knowledge:official",),
    )
    assert candidate.status is MemoryCandidateStatus.REJECTED
    assert candidate.rejection_reason == "knowledge_is_not_memory"


def test_task_result_candidate_has_exact_provenance_and_requires_review(service, clock) -> None:
    h = setup_memory(service, clock)
    candidate = h.propose(
        kind=MemoryProvenanceKind.TASK_RESULT,
        authority=MemoryAuthority.DERIVED,
    )
    assert candidate.status is MemoryCandidateStatus.UNDER_REVIEW


def test_tool_receipt_candidate_requires_canonical_exact_fact(service, clock) -> None:
    h = setup_memory(service, clock)

    class Tools:
        def evidence(self, run):
            return (Fact("pricing", "$49/month", "tool_receipt:receipt:pricing"),)

    h.memory.tools = Tools()
    candidate = h.propose(
        kind=MemoryProvenanceKind.TOOL_RECEIPT,
        authority=MemoryAuthority.OBSERVED,
        source_references=("tool_receipt:receipt:pricing",),
    )
    assert candidate.status is MemoryCandidateStatus.UNDER_REVIEW


def test_duplicate_candidate_is_idempotent(service, clock) -> None:
    h = setup_memory(service, clock)
    first = h.propose()
    second = h.propose()
    assert second.id == first.id
    assert len(h.memory_store.candidates(first.workspace_id)) == 1


def test_rejection_is_terminal_and_audited(service, clock) -> None:
    h = setup_memory(service, clock)
    candidate = h.propose()
    rejected = h.memory.reject(
        candidate.workspace_id, candidate.id, candidate.version, "reviewer", "not durable"
    )
    assert rejected.status is MemoryCandidateStatus.REJECTED
    assert EventType.MEMORY_CANDIDATE_REJECTED in {
        event.event_type for event in h.memory_store.events(candidate.workspace_id)
    }
    with pytest.raises(InvalidStateTransition):
        h.memory.reject(rejected.workspace_id, rejected.id, rejected.version, "reviewer", "again")


def test_revocation_excludes_new_retrieval_and_invalidates_active_pack(service, clock) -> None:
    h = setup_memory(service, clock)
    entry = h.approve(h.propose())
    pack = h.retrieve()
    revoked = h.memory.revoke(entry.workspace_id, entry.id, entry.version, "reviewer", "withdrawn")
    assert revoked.status is MemoryEntryStatus.REVOKED
    with pytest.raises(InvariantViolation, match="revoked_expired"):
        h.memory.active_pack(h.current())
    assert h.memory.get_context_pack(pack.workspace_id, pack.run_id, pack.id) == pack


def test_expiry_is_lazy_and_history_is_readable(service, clock) -> None:
    h = setup_memory(service, clock)
    entry = h.approve(h.propose(expires_in=10))
    pack = h.retrieve()
    clock.advance(timedelta(seconds=11))
    with pytest.raises(InvariantViolation, match="revoked_expired"):
        h.memory.active_pack(h.current())
    assert h.memory_store.entry(entry.workspace_id, entry.id).status is MemoryEntryStatus.ACTIVE
    assert h.memory.get_context_pack(pack.workspace_id, pack.run_id, pack.id) == pack


def test_supersession_is_atomic_and_preserves_history(service, clock) -> None:
    h = setup_memory(service, clock)
    old = h.approve(h.propose())
    newer = h.propose(content="$59/month")
    current = h.approve(newer, supersedes=old.id)
    assert current.supersedes_id == old.id
    assert h.memory_store.entry(old.workspace_id, old.id).status is MemoryEntryStatus.SUPERSEDED
    assert h.memory_store.entry(old.workspace_id, old.id).content == "$49/month"


def test_conflicting_memories_are_preserved_and_flagged(service, clock) -> None:
    h = setup_memory(service, clock)
    h.approve(h.propose())
    h.approve(h.propose(content="$59/month"))
    pack = h.retrieve()
    assert len(pack.result.hits) == 2
    assert all(hit.conflicting_entry_ids for hit in pack.result.hits)


def test_restricted_memory_requires_explicit_grant(service, clock) -> None:
    normal = setup_memory(service, clock)
    candidate = normal.propose(sensitivity=MemorySensitivity.RESTRICTED)
    normal.approve(candidate)
    pack = normal.retrieve()
    assert not pack.result.hits
    with pytest.raises(InvariantViolation, match="scope_or_run_state"):
        normal.retrieve(sensitivities=(MemorySensitivity.RESTRICTED,))


def test_restricted_memory_is_visible_with_an_exact_grant(service, clock) -> None:
    h = setup_memory(
        service,
        clock,
        sensitivities=(MemorySensitivity.NORMAL, MemorySensitivity.RESTRICTED),
    )
    entry = h.approve(h.propose(sensitivity=MemorySensitivity.RESTRICTED))
    pack = h.retrieve(sensitivities=(MemorySensitivity.RESTRICTED,))
    assert pack.result.hits[0].entry == entry


def test_runtime_receives_memory_separately_and_it_cannot_ground_completion(service, clock) -> None:
    h = setup_memory(service, clock)
    entry = h.approve(h.propose())
    pack = h.retrieve()
    model = FakeModel((completion(Fact("pricing", entry.content, f"memory:{entry.id}")),))
    runtime = AgentRuntimeService(
        h.runtime_store,
        clock,
        h.service.ids,
        model,
        memory=h.memory,
    )
    result = asyncio.run(runtime.drive(h.run.workspace_id, h.run.id, h.current().version))
    assert result.status.value == "failed"
    assert model.requests[0].memory_context == pack
    assert model.requests[0].knowledge_evidence is None


def test_runtime_revalidates_revocation_during_model_call(service, clock) -> None:
    h = setup_memory(service, clock)
    entry = h.approve(h.propose())
    h.retrieve()

    class RevokingModel(FakeModel):
        async def invoke(self, request):
            h.memory.revoke(entry.workspace_id, entry.id, entry.version, "reviewer", "concurrent")
            return decision("request_more_context", {"missing_fields": ["pricing"]})

    runtime = AgentRuntimeService(
        h.runtime_store, clock, h.service.ids, RevokingModel(()), memory=h.memory
    )
    result = asyncio.run(runtime.drive(h.run.workspace_id, h.run.id, h.current().version))
    assert result.status.value == "failed"
    assert result.error_code == "invariant_violation"


def test_cross_workspace_candidate_read_promote_retrieve_and_history_are_denied(
    service, clock
) -> None:
    h = setup_memory(service, clock)
    candidate = h.propose()
    other = h.service.create_workspace("Other")
    with pytest.raises(WorkspaceMismatch):
        h.memory_store.candidate(other.id, candidate.id)
    with pytest.raises(WorkspaceMismatch):
        h.memory.approve(other.id, candidate.id, candidate.version, "reviewer")
    entry = h.approve(candidate)
    with pytest.raises(WorkspaceMismatch):
        h.memory_store.entry(other.id, entry.id)
    pack = h.retrieve()
    with pytest.raises(WorkspaceMismatch):
        h.memory.get_context_pack(other.id, pack.run_id, pack.id)


def test_candidate_requires_canonical_successful_source_and_exact_reference(service, clock) -> None:
    h = setup_memory(service, clock)
    with pytest.raises(InvariantViolation, match="provenance"):
        h.propose(source_references=("fabricated",))
    command = ProposeMemoryCandidate(
        h.run.workspace_id,
        h.run.id,
        MemoryType.EPISODIC,
        "Paper Kite",
        "$49/month",
        SCOPE,
        MemoryProvenance(
            MemoryProvenanceKind.USER_STATEMENT, h.run.id, ("caller",), MemoryAuthority.STATED
        ),
    )
    with pytest.raises(InvariantViolation, match="successful_source_run"):
        h.memory.propose(command)


def test_version_conflicts_and_terminal_double_operations(service, clock) -> None:
    h = setup_memory(service, clock)
    candidate = h.propose()
    with pytest.raises(VersionConflict):
        h.memory.approve(candidate.workspace_id, candidate.id, Version(1), "reviewer")
    entry = h.approve(candidate)
    with pytest.raises(VersionConflict):
        h.memory.revoke(entry.workspace_id, entry.id, Version(2), "reviewer", "stale")
    revoked = h.memory.revoke(entry.workspace_id, entry.id, entry.version, "reviewer", "done")
    with pytest.raises(InvalidStateTransition):
        h.memory.revoke(revoked.workspace_id, revoked.id, revoked.version, "reviewer", "again")


def test_query_bounds_and_exact_subject_scope(service, clock) -> None:
    h = setup_memory(service, clock)
    h.approve(h.propose())
    run = h.current()
    with pytest.raises(InvariantViolation, match="query_bound"):
        MemoryQuery(run.workspace_id, "Paper Kite", "x", (SCOPE,), top_k=11)
    query = MemoryQuery(run.workspace_id, "Other subject", "pricing", (SCOPE,))
    assert not h.memory.retrieve(run.workspace_id, run.id, run.version, query).result.hits


def test_context_and_pack_limits(service, clock) -> None:
    h = setup_memory(service, clock)
    for index in range(6):
        h.approve(h.propose(content=f"$4{index}/month"))
    pack = h.retrieve()
    assert len(pack.result.hits) <= 5 and pack.context_chars <= 4000
    for _ in range(4):
        h.retrieve()
    with pytest.raises(InvariantViolation, match="scope_or_run_state"):
        h.retrieve()


def test_malicious_retriever_cannot_forge_results(service, clock) -> None:
    h = setup_memory(service, clock)
    entry = h.approve(h.propose())

    class Forged:
        def retrieve(self, query, eligible):
            from agent_company_os.domain.memory import MemoryHit

            return MemoryRetrievalResult((MemoryHit(entry, 999.0),))

    bad = MemoryService(h.memory_store, Forged(), clock, h.service.ids)
    run = h.current()
    with pytest.raises(InvariantViolation, match="unauthorized_or_forged"):
        bad.retrieve(
            run.workspace_id,
            run.id,
            run.version,
            MemoryQuery(run.workspace_id, "Paper Kite", "pricing", (SCOPE,)),
        )


def test_failed_promotion_rolls_back_candidate_and_entry(service, clock) -> None:
    h = setup_memory(service, clock)
    candidate = h.propose()
    original = h.memory_store.append_event

    def fail(event):
        if event.event_type is EventType.MEMORY_PROMOTED:
            raise RuntimeError("event failure")
        original(event)

    h.memory_store.append_event = fail  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        h.approve(candidate)
    assert h.memory_store.candidate(candidate.workspace_id, candidate.id) == candidate
    assert not h.memory_store.entries(candidate.workspace_id)


def test_serialization_exposes_separate_memory_pack_reference(service, clock) -> None:
    h = setup_memory(service, clock)
    h.approve(h.propose())
    pack = h.retrieve()
    serialized = serialize_run(h.current())
    assert serialized["active_memory_pack_id"] == str(pack.id)
    assert serialized["active_evidence_pack_id"] is None
    candidate = h.memory_store.candidates(h.run.workspace_id)[0]
    entry = h.memory_store.entries(h.run.workspace_id)[0]
    assert serialize_candidate(candidate)["status"] == "promoted"
    assert serialize_entry(entry)["reviewed_at"] == entry.reviewed_at.isoformat()


def test_authoritative_knowledge_conflict_is_flagged_without_overwrite(service, clock) -> None:
    h = setup_memory(service, clock)
    entry = h.approve(h.propose())

    class Knowledge:
        def active_pack(self, run):
            return None

        def evidence(self, run):
            return (Fact("pricing", "$79/month", "knowledge:official"),)

    h.memory.knowledge = Knowledge()
    pack = h.retrieve()
    assert pack.result.hits[0].entry == entry
    assert pack.result.hits[0].conflicts_with_knowledge
    assert entry.content == "$49/month"


def test_new_memory_does_not_rewrite_an_existing_pack(service, clock) -> None:
    h = setup_memory(service, clock)
    h.approve(h.propose())
    pack = h.retrieve()
    h.approve(h.propose(content="$59/month"))
    assert h.memory.active_pack(h.current()) == pack


def test_no_memory_grant_means_no_global_default(service, clock) -> None:
    h = setup_memory(service, clock)
    definition = research_brief_agent(h.run.workspace_id, AgentDefinitionId("ungranted"))
    assert not definition.memory_access.scopes
    with pytest.raises(InvariantViolation, match="scope_or_run_state"):
        run = h.current()
        h.memory.retrieve(
            run.workspace_id,
            run.id,
            run.version,
            MemoryQuery(
                run.workspace_id,
                "Paper Kite",
                "pricing",
                (MemoryScope(MemoryScopeKind.WORKSPACE, "*"),),
            ),
        )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_memory_policy_evaluation_fixture(case) -> None:
    content = "api_key=secret" if case["name"] == "secret_pattern" else "bounded content"
    candidate = MemoryCandidate(
        MemoryCandidateId(case["name"]),
        WorkspaceId("workspace"),
        MemoryType.SEMANTIC if "semantic" in case["name"] else MemoryType.EPISODIC,
        "subject",
        content,
        SCOPE,
        MemoryProvenance(
            MemoryProvenanceKind(case["kind"]),
            h_run_id(),
            ("source",),
            MemoryAuthority(case["authority"]),
        ),
        MemorySensitivity.RESTRICTED
        if case["name"] == "restricted_candidate"
        else MemorySensitivity.NORMAL,
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    result = MemoryPolicy().evaluate(candidate)
    expected = (
        MemoryPolicyDecision.REJECT
        if case["expected"] == "rejected"
        else MemoryPolicyDecision.REQUIRES_REVIEW
    )
    assert result.decision is expected


def h_run_id() -> AgentRunId:
    return AgentRunId("source-run")
