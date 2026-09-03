"""Offline Company Brain contract and adversarial evidence tests (brief A–T)."""

import asyncio
import json
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path

import pytest

from agent_company_os.adapters.clocks import FakeClock
from agent_company_os.adapters.fake_model import FakeModel
from agent_company_os.adapters.in_memory import InMemoryDomainStore
from agent_company_os.adapters.knowledge_ingestion import TextKnowledgeIngestor
from agent_company_os.adapters.knowledge_store import InMemoryKnowledgeStore
from agent_company_os.adapters.lexical_retrieval import LexicalKnowledgeRetriever
from agent_company_os.adapters.runtime_store import InMemoryRuntimeStore
from agent_company_os.adapters.tool_executors import CompanyFactLookup
from agent_company_os.adapters.tool_registry import ToolRegistry
from agent_company_os.application.knowledge import (
    KnowledgeService,
    PublishKnowledgeSource,
    with_knowledge,
)
from agent_company_os.application.research_agent import research_brief_agent, with_read_only_tools
from agent_company_os.application.runtime import AgentRuntimeService
from agent_company_os.application.runtime_serialization import serialize_run
from agent_company_os.application.service import (
    CreateExecutionCommand,
    CreateGoalCommand,
    CreateTaskAttemptCommand,
    CreateTaskCommand,
    DomainService,
)
from agent_company_os.application.tool_runtime import ToolRuntimeService
from agent_company_os.application.tool_validation import validate_output
from agent_company_os.domain.agent import (
    AgentDefinitionId,
    AgentRun,
    Fact,
    RuntimeLimits,
    SourceText,
    SuppliedContext,
)
from agent_company_os.domain.chunking import chunk_content
from agent_company_os.domain.errors import (
    EntityNotFound,
    InvariantViolation,
    VersionConflict,
    WorkspaceMismatch,
)
from agent_company_os.domain.events import EventType
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.knowledge import (
    EvidenceCandidate,
    EvidencePack,
    IngestionLimits,
    KnowledgeChunkId,
    KnowledgeQuery,
    KnowledgeScope,
    KnowledgeSource,
    KnowledgeSourceVersion,
    RetrievalResult,
    SourceType,
    TrustClass,
    digest,
    serialize_pack,
)
from agent_company_os.domain.tools import (
    CompanyLookupInput,
    ExecutorKind,
    ToolDefinition,
    ToolFailure,
    ToolId,
    ToolVersion,
)
from agent_company_os.ports.model import AgentModelRequest

FIXTURES = Path(__file__).parent / "fixtures/knowledge"
CASES = json.loads((Path(__file__).parent / "fixtures/agent_eval/knowledge_cases.json").read_text())


def decision(kind: str, payload: object) -> str:
    return json.dumps({"schema_version": 1, "action_type": kind, "payload": payload})


def completion(facts: tuple[Fact, ...], gaps: tuple[str, ...] = ()) -> str:
    return decision(
        "complete_task",
        {
            "findings": [{"key": f.key, "value": f.value, "source_id": f.source_id} for f in facts],
            "gaps": gaps,
        },
    )


WAIT = decision("request_more_context", {"missing_fields": ["pricing"]})


@dataclass
class Harness:
    service: DomainService
    knowledge: KnowledgeService
    store: InMemoryKnowledgeStore
    runtime: AgentRuntimeService
    run: AgentRun
    sources: tuple[KnowledgeSource, ...]

    def current(self) -> AgentRun:
        return self.store.runtime.get_run(self.run.workspace_id, self.run.id)

    def retrieve(self, query: KnowledgeQuery | None = None) -> EvidencePack:
        run = self.current()
        return self.knowledge.retrieve(
            run.workspace_id,
            run.id,
            run.version,
            query or KnowledgeQuery(run.workspace_id, "pricing"),
        )

    def drive(self, responses: tuple[str | Exception, ...]) -> AgentRun:
        self.runtime.model = FakeModel(responses)
        run = self.current()
        return asyncio.run(self.runtime.drive(run.workspace_id, run.id, run.version))

    def facts(self) -> tuple[Fact, ...]:
        return self.knowledge.evidence(self.current())


def setup(
    service: DomainService,
    clock: FakeClock,
    *,
    files: tuple[str, ...] = ("pricing_v1.json",),
    grants: bool = True,
    supplied: bool = False,
    required: tuple[str, ...] = ("pricing",),
    tools: bool = False,
    limits: RuntimeLimits | None = None,
) -> Harness:
    workspace = service.create_workspace("Fictional Aurora Desk")
    goal = service.create_goal(
        CreateGoalCommand(workspace.id, "Produce evidence-backed brief", ("Grounded",))
    )
    goal = service.activate_goal(goal.id, goal.version)
    task = service.create_task(
        CreateTaskCommand(workspace.id, goal.id, "Research pricing", ("Exact facts",))
    )
    task = service.ready_task(task.id, task.version)
    task = service.start_task(task.id, task.version)
    execution = service.create_execution(
        CreateExecutionCommand(workspace.id, goal.id, "test-user", 5)
    )
    execution = service.start_execution(execution.id, execution.version)
    attempt = service.create_task_attempt(
        CreateTaskAttemptCommand(workspace.id, task.id, execution.id)
    )
    attempt = service.start_task_attempt(attempt.id, attempt.version)
    assert isinstance(service.store, InMemoryDomainStore)
    runtime_store = InMemoryRuntimeStore(service.store)
    store = InMemoryKnowledgeStore(runtime_store)
    knowledge = KnowledgeService(
        store, TextKnowledgeIngestor(), LexicalKnowledgeRetriever(), clock, service.ids
    )
    sources = tuple(
        knowledge.publish_source(
            PublishKnowledgeSource(
                workspace.id,
                filename,
                SourceType.STRUCTURED_FACTS
                if filename.endswith("json")
                else SourceType.MARKDOWN
                if filename.endswith("md")
                else SourceType.TEXT,
                TrustClass.AUTHORITATIVE,
                (FIXTURES / filename).read_bytes(),
            )
        )
        for filename in files
    )
    definition = research_brief_agent(workspace.id, AgentDefinitionId(str(service.ids.event_id())))
    runtime_store.publish(definition)
    tool_service = None
    if tools:
        registry = ToolRegistry()
        tool = ToolVersion(
            ToolDefinition(ToolId("company"), workspace.id, "Company lookup", "Fixture"),
            Version(1),
            ExecutorKind.COMPANY_LOOKUP,
            "company_lookup.v1",
        )
        registry.publish(tool, CompanyFactLookup({"Aurora": (Fact("stock", "12", "inventory"),)}))
        definition = with_read_only_tools(definition, (tool.grant,))
        runtime_store.publish(definition)
        tool_service = ToolRuntimeService(runtime_store, registry, clock, service.ids)
    if grants:
        definition = with_knowledge(definition, KnowledgeScope(tuple(s.id for s in sources)))
        runtime_store.publish(definition)
    runtime = AgentRuntimeService(
        runtime_store, clock, service.ids, FakeModel(()), tool_service, knowledge
    )
    context = SuppliedContext(
        workspace.id,
        task.id,
        required,
        (Fact("pricing", "$49/month", "caller"),) if supplied else (),
    )
    run = runtime.start(
        workspace.id, definition.definition.id, definition.version, attempt.id, context, limits
    )
    return Harness(service, knowledge, store, runtime, run, sources)


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda c: c["name"])
def test_knowledge_eval(service: DomainService, clock: FakeClock, case: dict[str, object]) -> None:
    name = case["name"]
    files: tuple[str, ...] = ("pricing_v1.json",)
    if name == "conflicting_knowledge":
        files += ("sales_notes.json",)
    if name == "source_prompt_injection":
        files += ("injection.md",)
    required = ("pricing", "plan") if name == "conflicting_knowledge" else ("pricing",)
    if name == "tool_vs_knowledge":
        required = ("pricing", "stock")
    h = setup(
        service,
        clock,
        files=files,
        grants=name != "unauthorized_knowledge_source",
        supplied=name == "knowledge_not_needed",
        required=required,
        tools=name == "tool_vs_knowledge",
    )
    if name == "stale_knowledge_version":
        old = h.retrieve()
        s = h.sources[0]
        h.knowledge.publish_version(
            s.workspace_id, s.id, s.version, (FIXTURES / "pricing_v2.json").read_bytes()
        )
        assert old.result.candidates[0].chunk.fact is not None
        assert old.result.candidates[0].chunk.fact.value == "$49/month"
    if name == "unauthorized_knowledge_source":
        with pytest.raises(InvariantViolation, match="scope_denied"):
            h.retrieve()
        assert not h.store.packs(h.run.workspace_id, h.run.id)
        return
    if case["retrieve"]:
        pack = h.retrieve(
            KnowledgeQuery(h.run.workspace_id, str(case["query"]), max_context_chars=8000)
        )
        assert pack.context_chars <= pack.query.max_context_chars
    facts = h.facts() or h.run.context.facts
    responses: tuple[str | Exception, ...]
    if name == "missing_knowledge":
        responses = (WAIT,)
    elif name == "source_prompt_injection":
        responses = (decision("call_tool", {"tool_id": "delete_database", "arguments": {}}),)
    elif name == "fabricated_knowledge_reference":
        responses = (completion((replace(facts[0], source_id=facts[0].source_id + ":fake"),)),)
    elif name == "conflicting_knowledge":
        assert {f.value for f in facts if f.key == "pricing"} == {"$49/month", "$45/month"}
        responses = (completion(tuple(f for f in facts if f.key == "plan"), ("pricing",)),)
    elif name == "tool_vs_knowledge":
        tool_fact = Fact("stock", "12", "tool_receipt:test-tool-receipt-0001:inventory")
        responses = (
            decision("call_tool", {"tool_id": "company", "arguments": {"company_name": "Aurora"}}),
            completion((*facts, tool_fact)),
        )
    else:
        responses = (completion(facts),)
    result = h.drive(responses)
    assert result.status.value == case["expected"]
    assert isinstance(h.runtime.model, FakeModel)
    request = h.runtime.model.requests[0]
    if case["retrieve"]:
        assert request.knowledge_evidence is not None
        assert request.knowledge_evidence.run_id == h.run.id
        assert not request.supplied_data.facts
    else:
        assert request.knowledge_evidence is None
    if name == "stale_knowledge_version":
        assert result.result is not None and result.result.findings[0].value == "$59/month"
    if name == "query_injection":
        assert len(h.run.definition_version.knowledge_scope.source_ids) == 1
    if name == "tool_vs_knowledge":
        assert request.available_tools and len(h.runtime.model.requests) == 2


def test_history_eviction_and_disable(service: DomainService, clock: FakeClock) -> None:
    h = setup(service, clock)
    first = h.retrieve()
    first_json = serialize_pack(first)
    source = h.sources[0]
    clock.advance(timedelta(seconds=1))
    changed = h.knowledge.publish_version(
        source.workspace_id, source.id, source.version, (FIXTURES / "pricing_v2.json").read_bytes()
    )
    assert h.knowledge.active_pack(h.current()) == first  # exact captured version, not latest
    second = h.retrieve()
    assert first.result.candidates[0].chunk.source_version == Version(1)
    assert second.result.candidates[0].chunk.source_version == Version(2)
    assert (
        second.result.candidates[0].source_created_at > first.result.candidates[0].source_created_at
    )
    assert (
        serialize_pack(h.knowledge.get_evidence_pack(h.run.workspace_id, h.run.id, first.id))
        == first_json
    )
    assert h.knowledge.active_pack(h.current()) == second
    h.knowledge.disable_source(changed.workspace_id, changed.id, changed.version)
    with pytest.raises(InvariantViolation, match="revoked"):
        h.knowledge.active_pack(h.current())
    empty = h.retrieve()
    assert empty.result.candidates == ()
    assert h.knowledge.get_evidence_pack(h.run.workspace_id, h.run.id, second.id) == second
    with pytest.raises(InvariantViolation, match="disabled"):
        current = h.store.source(source.workspace_id, source.id)
        h.knowledge.publish_version(
            source.workspace_id,
            source.id,
            current.version,
            (FIXTURES / "pricing_v2.json").read_bytes(),
        )


@pytest.mark.parametrize(
    "raw",
    [b"", b"\xff", b"bad\x00text", b"x" * 32769, b"x" * 16001, b"\t\n"],
    ids=["empty", "bad-utf8", "control", "byte-limit", "character-limit", "blank"],
)
def test_bad_text_ingestion(raw: bytes) -> None:
    with pytest.raises(InvariantViolation):
        TextKnowledgeIngestor().normalize(raw, SourceType.TEXT, IngestionLimits())


@pytest.mark.parametrize(
    "raw",
    [
        b"{}",
        b'{"company":"X","facts":[]}',
        b'{"company":"X","company":"Y","facts":[]}',
        b'{"company":"X","facts":[{"key":"pricing","value":4}]}',
        b'{"company":"X","facts":[{"key":"a","value":"b","source_id":"knowledge:fake"}]}',
    ],
)
def test_bad_fact_schema(raw: bytes) -> None:
    with pytest.raises(InvariantViolation):
        TextKnowledgeIngestor().normalize(raw, SourceType.STRUCTURED_FACTS, IngestionLimits())


def test_normalization_chunking_and_limits(service: DomainService, clock: FakeClock) -> None:
    h = setup(service, clock)
    ingestor = TextKnowledgeIngestor()
    raw = b"First paragraph.\r\n\r\nSecond paragraph with a longer line.\r\n"
    content = ingestor.normalize(raw, SourceType.MARKDOWN, IngestionLimits())
    assert "\r" not in content.text and content.text.endswith("\n")
    version = KnowledgeSourceVersion(
        replace(h.sources[0], source_type=SourceType.MARKDOWN),
        content,
        digest(content.text),
        clock.now(),
        IngestionLimits(chunk_chars=18),
    )
    chunks = chunk_content(version)
    assert chunks == chunk_content(version) and len(chunks) > 2
    assert all(len(c.text) <= 18 and c.content_hash == digest(c.text) for c in chunks)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    assert len({c.id for c in chunks}) == len(chunks)
    with pytest.raises(InvariantViolation, match="chunk_count"):
        chunk_content(replace(version, limits=IngestionLimits(chunk_chars=3, chunks=1)))
    with pytest.raises(InvariantViolation):
        IngestionLimits(chunks=129)
    with pytest.raises(InvariantViolation, match="fact_count"):
        ingestor.normalize(
            (FIXTURES / "pricing_v1.json").read_bytes(),
            SourceType.STRUCTURED_FACTS,
            IngestionLimits(facts=1),
        )


def test_ranking_bounds_and_irrelevant_exclusion(service: DomainService, clock: FakeClock) -> None:
    h = setup(
        service,
        clock,
        files=(
            "pricing_v1.json",
            "sales_notes.json",
            "product.md",
            "refund_policy.txt",
            "competitors.json",
        ),
    )
    q = KnowledgeQuery(
        h.run.workspace_id, "pricing plan", top_k=10, max_per_source=1, max_context_chars=2400
    )
    first, second = h.retrieve(q), h.retrieve(q)
    assert first.result == second.result
    assert first.context_chars <= 2400 and first.result.truncated
    assert all(c.chunk.source_id != h.sources[3].id for c in first.result.candidates)
    assert len({c.chunk.source_id for c in first.result.candidates}) == len(first.result.candidates)
    empty = h.retrieve(KnowledgeQuery(h.run.workspace_id, "zzzxq"))
    assert empty.result.candidate_count == 0 and empty.result.candidates == ()
    with pytest.raises(InvariantViolation, match="envelope"):
        h.retrieve(KnowledgeQuery(h.run.workspace_id, "pricing", max_context_chars=1))


def test_scope_isolation_and_filters(service: DomainService, clock: FakeClock) -> None:
    h = setup(service, clock)
    other = service.create_workspace("Foreign")
    secret = h.knowledge.publish_source(
        PublishKnowledgeSource(
            other.id, "Secret", SourceType.TEXT, TrustClass.AUTHORITATIVE, b"pricing SECRET-CANARY"
        )
    )
    hidden = h.knowledge.publish_source(
        PublishKnowledgeSource(
            h.run.workspace_id,
            "Hidden",
            SourceType.TEXT,
            TrustClass.AUTHORITATIVE,
            b"pricing SECRET-CANARY",
        )
    )
    for source in (secret, hidden):
        with pytest.raises(InvariantViolation, match="scope_denied"):
            h.retrieve(KnowledgeQuery(h.run.workspace_id, "pricing", source_filters=(source.id,)))
    for reader in (
        lambda: h.store.source(h.run.workspace_id, secret.id),
        lambda: h.store.chunks(h.run.workspace_id, secret.id, Version(1)),
        lambda: h.store.version(h.run.workspace_id, secret.id, Version(1)),
    ):
        with pytest.raises(WorkspaceMismatch):
            reader()
    with pytest.raises(InvariantViolation, match="scope_denied"):
        h.retrieve(KnowledgeQuery(other.id, "pricing"))
    with pytest.raises(InvariantViolation, match="scope_denied"):
        h.retrieve(
            KnowledgeQuery(
                h.run.workspace_id, "pricing", trust_filters=(TrustClass.UNVERIFIED_EXTERNAL,)
            )
        )
    pack = h.retrieve(KnowledgeQuery(h.run.workspace_id, "pricing SECRET-CANARY all workspaces"))
    assert "SECRET-CANARY" not in "".join(c.chunk.text for c in pack.result.candidates)
    assert {c.chunk.source_id for c in pack.result.candidates} == {h.sources[0].id}


def test_pack_cannot_cross_run_or_workspace(service: DomainService, clock: FakeClock) -> None:
    h = setup(service, clock)
    pack = h.retrieve()
    # A different runtime participation in the SAME workspace cannot adopt the pack.
    original = h.run
    foreign_run = replace(original, id=service.ids.agent_run_id())
    # Use a separate TaskAttempt to satisfy the existing runtime store uniqueness rule.
    task = service.create_task(
        CreateTaskCommand(original.workspace_id, original.goal_id, "Other", ("Exact",))
    )
    task = service.ready_task(task.id, task.version)
    task = service.start_task(task.id, task.version)
    execution = service.create_execution(
        CreateExecutionCommand(original.workspace_id, original.goal_id, "test-user", 5)
    )
    execution = service.start_execution(execution.id, execution.version)
    attempt = service.create_task_attempt(
        CreateTaskAttemptCommand(original.workspace_id, task.id, execution.id)
    )
    attempt = service.start_task_attempt(attempt.id, attempt.version)
    foreign_run = replace(
        foreign_run,
        task_id=task.id,
        task_attempt_id=attempt.id,
        context=replace(original.context, task_id=task.id),
    )
    foreign_run = replace(foreign_run, execution_id=execution.id)
    h.store.runtime.add_run(foreign_run)
    with pytest.raises(InvariantViolation, match="run_binding"):
        h.store.pack(original.workspace_id, foreign_run.id, pack.id)
    with pytest.raises(InvariantViolation, match="run_binding"):
        h.knowledge.active_pack(replace(foreign_run, working_state=h.current().working_state))
    other = service.create_workspace("Foreign")
    with pytest.raises(WorkspaceMismatch):
        h.store.pack(other.id, original.id, pack.id)


def test_free_text_is_visible_but_not_an_entailment_oracle(
    service: DomainService, clock: FakeClock
) -> None:
    h = setup(service, clock, files=("refund_policy.txt",))
    pack = h.retrieve(KnowledgeQuery(h.run.workspace_id, "refund"))
    assert pack.result.candidates and not h.facts()
    ref = pack.result.candidates[0].chunk.reference
    result = h.drive((completion((Fact("pricing", "Free refunds forever", ref),)),))
    assert result.status.value == "failed"
    assert h.knowledge.get_evidence_pack(h.run.workspace_id, h.run.id, pack.id) == pack
    assert isinstance(h.runtime.model, FakeModel)
    assert h.runtime.model.requests[0].knowledge_evidence == pack


@pytest.mark.parametrize("failure_point", ["publish_audit", "pack_save", "run_save", "pack_audit"])
def test_atomic_failures(
    service: DomainService, clock: FakeClock, monkeypatch: pytest.MonkeyPatch, failure_point: str
) -> None:
    h = setup(service, clock)
    source = h.sources[0]
    before = h.current()
    before_events = tuple(h.store.runtime.events(before.workspace_id))

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected storage fault")

    if failure_point == "publish_audit":
        monkeypatch.setattr(h.store, "append_event", fail)
        with pytest.raises(RuntimeError):
            h.knowledge.publish_version(
                source.workspace_id,
                source.id,
                source.version,
                (FIXTURES / "pricing_v2.json").read_bytes(),
            )
        assert h.store.source(source.workspace_id, source.id) == source
        with pytest.raises(EntityNotFound):
            h.store.chunks(source.workspace_id, source.id, Version(2))
    else:
        target, method = (
            (h.store, "save_pack")
            if failure_point == "pack_save"
            else (h.store.runtime, "save_run" if failure_point == "run_save" else "append_event")
        )
        monkeypatch.setattr(target, method, fail)
        with pytest.raises(RuntimeError):
            h.retrieve()
        assert h.current() == before
        assert not h.store.packs(before.workspace_id, before.id)
        assert tuple(h.store.runtime.events(before.workspace_id)) == before_events


def test_concurrency_deadline_query_budget_and_history(
    service: DomainService, clock: FakeClock
) -> None:
    h = setup(service, clock)
    pack = h.retrieve()
    with pytest.raises(VersionConflict):
        h.knowledge.retrieve(h.run.workspace_id, h.run.id, h.run.version, pack.query)
    for _ in range(4):
        h.retrieve()
    with pytest.raises(InvariantViolation, match="queries_per_run"):
        h.retrieve()
    assert len(h.store.packs(h.run.workspace_id, h.run.id)) == 5
    clock.advance(timedelta(seconds=60))
    with pytest.raises(InvariantViolation, match="idle_active"):
        h.retrieve()


def test_inflight_retrieval_and_revocation(service: DomainService, clock: FakeClock) -> None:
    h = setup(service, clock)
    h.retrieve()
    facts = h.facts()

    def revoke(request: AgentModelRequest) -> None:
        assert request.knowledge_evidence is not None
        with pytest.raises(InvariantViolation, match="idle_active"):
            h.retrieve()
        source = h.sources[0]
        h.knowledge.disable_source(source.workspace_id, source.id, source.version)

    h.runtime.model = FakeModel((completion(facts),), on_invoke=revoke)
    current = h.current()
    result = asyncio.run(h.runtime.drive(current.workspace_id, current.id, current.version))
    assert result.status.value == "failed" and result.result is None
    assert h.store.packs(current.workspace_id, current.id)


def test_context_budget_and_no_adapter(service: DomainService, clock: FakeClock) -> None:
    h = setup(service, clock, limits=RuntimeLimits(max_context_chars=900))
    h.retrieve()
    result = h.drive((WAIT,))
    assert result.error_code == "context_overflow"
    assert isinstance(h.runtime.model, FakeModel) and not h.runtime.model.requests


def test_source_event_and_pack_serialization(service: DomainService, clock: FakeClock) -> None:
    h = setup(service, clock)
    pack = h.retrieve(KnowledgeQuery(h.run.workspace_id, "pricing PRIVATE-QUERY-CANARY"))
    data = json.loads(json.dumps(serialize_pack(pack)))
    assert data["schema_version"] == 1 and data["id"] == str(pack.id)
    assert data["created_at"].endswith("+00:00")
    assert data["candidates"][0]["source_version"] == 1
    assert data["candidates"][0]["reference"].startswith("knowledge:")
    events = h.store.runtime.events(h.run.workspace_id)
    event = next(e for e in events if e.event_type is EventType.KNOWLEDGE_QUERY_EXECUTED)
    metadata = dict(event.metadata)
    assert metadata["evidence_pack_id"] == str(pack.id)
    assert metadata["strategy"] == "lexical-overlap" and metadata["duration_ms"] == "0"
    assert "PRIVATE-QUERY-CANARY" not in repr(event) and "$49/month" not in repr(event)
    source_event = h.store.events(h.run.workspace_id)[0]
    assert source_event.subject_id == str(h.sources[0].id)
    with pytest.raises(WorkspaceMismatch):
        h.store.append_event(
            replace(source_event, workspace_id=service.create_workspace("Other").id)
        )


def test_reserved_provenance_and_chunk_forgery(service: DomainService, clock: FakeClock) -> None:
    h = setup(service, clock)
    pack = h.retrieve()
    candidate = pack.result.candidates[0]
    with pytest.raises(InvariantViolation):
        replace(h.run.context, facts=(Fact("pricing", "$49/month", candidate.chunk.reference),))
    with pytest.raises(InvariantViolation):
        replace(h.run.context, source_texts=(SourceText(candidate.chunk.reference, "fake"),))

    class PoisonedRetriever:
        def retrieve(
            self, query: KnowledgeQuery, eligible: tuple[EvidenceCandidate, ...]
        ) -> RetrievalResult:
            forged = replace(
                eligible[0],
                chunk=replace(eligible[0].chunk, id=KnowledgeChunkId("fake")),
                score=1.0,
            )
            return RetrievalResult((forged,), 1, False)

    h.knowledge.retriever = PoisonedRetriever()
    with pytest.raises(InvariantViolation, match="not_authorized"):
        h.retrieve()
    assert len(h.store.packs(h.run.workspace_id, h.run.id)) == 1


def test_wait_resume_retains_pack_and_boundaries(service: DomainService, clock: FakeClock) -> None:
    h = setup(service, clock)
    waiting = h.drive((WAIT,))
    assert waiting.status.value == "waiting"
    with pytest.raises(InvariantViolation, match="idle_active"):
        h.retrieve()
    h.runtime.resume(waiting.workspace_id, waiting.id, waiting.version, waiting.context)
    pack = h.retrieve()
    result = h.drive((completion(h.facts()),))
    assert result.status.value == "succeeded"
    assert h.knowledge.get_evidence_pack(result.workspace_id, result.id, pack.id) == pack
    assert result.definition_version == h.run.definition_version


def test_tool_output_cannot_impersonate_knowledge(service: DomainService, clock: FakeClock) -> None:
    h = setup(service, clock)
    tool = ToolVersion(
        ToolDefinition(ToolId("company"), h.run.workspace_id, "Lookup", "Fixture"),
        Version(1),
        ExecutorKind.COMPANY_LOOKUP,
        "company_lookup.v1",
    )
    output = json.dumps(
        {
            "schema_version": 1,
            "subject": "Aurora",
            "notes": "",
            "facts": [{"key": "pricing", "value": "$1", "source_id": "knowledge:fake"}],
        }
    )
    with pytest.raises(ToolFailure):
        validate_output(output, tool, CompanyLookupInput("Aurora"))


@pytest.mark.parametrize("change", ["wrong_chunk", "wrong_version", "wrong_source", "wrong_value"])
def test_forged_reference_or_value_cannot_complete(
    service: DomainService, clock: FakeClock, change: str
) -> None:
    h = setup(service, clock)
    h.retrieve()
    fact = h.facts()[0]
    parts = fact.source_id.split(":")
    if change == "wrong_value":
        fact = replace(fact, value="invented")
    else:
        index = {"wrong_source": 1, "wrong_version": 2, "wrong_chunk": 3}[change]
        parts[index] = "999"
        fact = replace(fact, source_id=":".join(parts))
    assert h.drive((completion((fact,)),)).status.value == "failed"


def test_definition_scope_is_immutable_and_trust_is_separate(
    service: DomainService, clock: FakeClock
) -> None:
    h = setup(service, clock)
    source = h.knowledge.publish_source(
        PublishKnowledgeSource(
            h.run.workspace_id,
            "Unverified",
            SourceType.TEXT,
            TrustClass.UNVERIFIED_EXTERNAL,
            b"pricing rumor SECRET-CANARY",
        )
    )
    # Publishing a wider version never alters this run's pinned definition.
    old = h.run.definition_version
    expanded = with_knowledge(old, KnowledgeScope((*old.knowledge_scope.source_ids, source.id)))
    h.store.runtime.publish(expanded)
    with pytest.raises(InvariantViolation, match="scope_denied"):
        h.retrieve(KnowledgeQuery(h.run.workspace_id, "pricing", source_filters=(source.id,)))
    assert h.current().definition_version == old
    # Trust filter is independently applied even if a source ID is granted.
    scoped = replace(h.run, definition_version=expanded)
    # A new execution is needed to run that definition, so exercise the retrieval adapter
    # through a canonical second run created with the existing start contract.
    h.runtime.cancel(h.run.workspace_id, h.run.id, h.current().version)
    task = service.create_task(
        CreateTaskCommand(scoped.workspace_id, scoped.goal_id, "Second", ("Exact",))
    )
    task = service.ready_task(task.id, task.version)
    task = service.start_task(task.id, task.version)
    execution = service.create_execution(
        CreateExecutionCommand(scoped.workspace_id, scoped.goal_id, "test-user", 5)
    )
    execution = service.start_execution(execution.id, execution.version)
    attempt = service.create_task_attempt(
        CreateTaskAttemptCommand(scoped.workspace_id, task.id, execution.id)
    )
    attempt = service.start_task_attempt(attempt.id, attempt.version)
    run = h.runtime.start(
        scoped.workspace_id,
        expanded.definition.id,
        expanded.version,
        attempt.id,
        replace(scoped.context, task_id=task.id),
    )
    pack = h.knowledge.retrieve(
        run.workspace_id, run.id, run.version, KnowledgeQuery(run.workspace_id, "pricing")
    )
    assert all(c.trust is not TrustClass.UNVERIFIED_EXTERNAL for c in pack.result.candidates)
    assert "SECRET-CANARY" not in repr(pack)


def test_evicted_pack_cannot_ground_current_completion(
    service: DomainService, clock: FakeClock
) -> None:
    h = setup(service, clock)
    first = h.retrieve()
    facts = h.facts()
    empty = h.retrieve(KnowledgeQuery(h.run.workspace_id, "zzzxq"))
    assert serialize_run(h.current())["active_evidence_pack_id"] == str(empty.id)
    assert h.drive((completion(facts),)).status.value == "failed"
    assert h.knowledge.get_evidence_pack(h.run.workspace_id, h.run.id, first.id) == first


def test_source_publish_cas_and_chunk_binding(service: DomainService, clock: FakeClock) -> None:
    h = setup(service, clock)
    source = h.sources[0]
    with pytest.raises(VersionConflict):
        h.knowledge.publish_version(
            source.workspace_id, source.id, Version(9), (FIXTURES / "pricing_v2.json").read_bytes()
        )
    old = h.store.version(source.workspace_id, source.id, Version(1))
    updated = replace(old, source=replace(source, version=Version(2), content_version=Version(2)))
    chunks = chunk_content(updated)
    with pytest.raises(InvariantViolation, match="chunk_source_binding"):
        h.store.publish(
            updated, (replace(chunks[0], id=KnowledgeChunkId("forged")), *chunks[1:]), Version(1)
        )
    assert h.store.source(source.workspace_id, source.id) == source


@pytest.mark.parametrize(
    "field,value",
    [("top_k", 11), ("max_context_chars", 12001), ("max_per_source", 6), ("top_k", True)],
)
def test_query_hard_limits(field: str, value: int) -> None:
    with pytest.raises(InvariantViolation):
        query = KnowledgeQuery(WorkspaceId("ws"), "pricing")
        if field == "top_k":
            replace(query, top_k=value)
        elif field == "max_context_chars":
            replace(query, max_context_chars=value)
        else:
            replace(query, max_per_source=value)


def test_missing_knowledge_adapter_fails_closed(service: DomainService, clock: FakeClock) -> None:
    h = setup(service, clock)
    h.retrieve()
    h.runtime.knowledge = None
    assert h.drive((completion(h.facts()),)).status.value == "failed"
    assert isinstance(h.runtime.model, FakeModel) and not h.runtime.model.requests


def test_direct_pack_store_rejects_stale_or_oversized_evidence(
    service: DomainService, clock: FakeClock
) -> None:
    h = setup(service, clock)
    pack = h.retrieve()
    with pytest.raises(InvariantViolation, match="identity_or_limit"):
        h.store.save_pack(
            replace(
                pack,
                id=service.ids.evidence_pack_id(),
                query=replace(pack.query, max_context_chars=1),
            )
        )
    source = h.sources[0]
    h.knowledge.publish_version(
        source.workspace_id, source.id, source.version, (FIXTURES / "pricing_v2.json").read_bytes()
    )
    with pytest.raises(InvariantViolation, match="evidence_binding"):
        h.store.save_pack(replace(pack, id=service.ids.evidence_pack_id()))
