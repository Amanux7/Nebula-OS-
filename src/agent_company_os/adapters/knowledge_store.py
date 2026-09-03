"""In-process knowledge records sharing the runtime transaction lock and rollback."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace

from agent_company_os.domain.agent import AgentRunId, AgentRunStatus
from agent_company_os.domain.chunking import chunk_content
from agent_company_os.domain.errors import (
    EntityNotFound,
    InvariantViolation,
    VersionConflict,
    WorkspaceMismatch,
)
from agent_company_os.domain.events import Event
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.knowledge import (
    EvidencePack,
    EvidencePackId,
    KnowledgeChunk,
    KnowledgeSource,
    KnowledgeSourceId,
    KnowledgeSourceVersion,
    SourceStatus,
)
from agent_company_os.domain.transitions import SubjectType
from agent_company_os.ports.runtime_store import RuntimeStore


class InMemoryKnowledgeStore:
    def __init__(self, runtime: RuntimeStore) -> None:
        self.runtime = runtime
        self._sources: dict[KnowledgeSourceId, KnowledgeSource] = {}
        self._versions: dict[tuple[KnowledgeSourceId, Version], KnowledgeSourceVersion] = {}
        self._chunks: dict[tuple[KnowledgeSourceId, Version], tuple[KnowledgeChunk, ...]] = {}
        self._packs: dict[EvidencePackId, EvidencePack] = {}
        self._events: list[Event] = []

    @contextmanager
    def atomic(self) -> Iterator[None]:
        with self.runtime.atomic():
            snapshot = (
                self._sources.copy(),
                self._versions.copy(),
                self._chunks.copy(),
                self._packs.copy(),
                self._events.copy(),
            )
            try:
                yield
            except BaseException:
                self._sources, self._versions, self._chunks, self._packs, self._events = snapshot
                raise

    def source(self, workspace_id: WorkspaceId, source_id: KnowledgeSourceId) -> KnowledgeSource:
        try:
            source = self._sources[source_id]
        except KeyError as error:
            raise EntityNotFound("KnowledgeSource", str(source_id)) from error
        if source.workspace_id != workspace_id:
            raise WorkspaceMismatch("knowledge", str(workspace_id), str(source.workspace_id))
        return source

    def version(
        self, workspace_id: WorkspaceId, source_id: KnowledgeSourceId, version: Version
    ) -> KnowledgeSourceVersion:
        self.source(workspace_id, source_id)
        try:
            return self._versions[(source_id, version)]
        except KeyError as error:
            raise EntityNotFound("KnowledgeSourceVersion", str(source_id)) from error

    def chunks(
        self, workspace_id: WorkspaceId, source_id: KnowledgeSourceId, version: Version
    ) -> tuple[KnowledgeChunk, ...]:
        self.version(workspace_id, source_id, version)
        return self._chunks[(source_id, version)]

    def publish(
        self,
        version: KnowledgeSourceVersion,
        chunks: tuple[KnowledgeChunk, ...],
        expected: Version | None,
    ) -> None:
        with self.atomic():
            source = version.source
            self.runtime.domain.get_workspace(source.workspace_id)
            if source.id in self._sources:
                previous = self.source(source.workspace_id, source.id)
                if expected != previous.version:
                    raise VersionConflict(
                        "KnowledgeSource",
                        str(source.id),
                        expected.value if expected else 0,
                        previous.version.value,
                    )
                correct = replace(
                    previous,
                    version=previous.version.next(),
                    content_version=previous.content_version.next(),
                )
                if source != correct or previous.status is not SourceStatus.ACTIVE:
                    raise InvariantViolation("knowledge_lineage_immutable_or_disabled")
            elif (
                expected is not None
                or source.version != Version(1)
                or source.content_version != Version(1)
                or source.status is not SourceStatus.ACTIVE
            ):
                raise InvariantViolation("knowledge_initial_version")
            elif sum(s.workspace_id == source.workspace_id for s in self._sources.values()) >= 100:
                raise InvariantViolation("knowledge_workspace_source_limit")
            key = (source.id, source.content_version)
            if key in self._versions or source.content_version.value > 20:
                raise InvariantViolation("knowledge_version_history_bound")
            if chunks != chunk_content(version):
                raise InvariantViolation("knowledge_chunk_source_binding")
            self._sources[source.id] = source
            self._versions[key] = version
            self._chunks[key] = chunks

    def disable(
        self, workspace_id: WorkspaceId, source_id: KnowledgeSourceId, expected: Version
    ) -> KnowledgeSource:
        with self.atomic():
            previous = self.source(workspace_id, source_id)
            if expected != previous.version:
                raise VersionConflict(
                    "KnowledgeSource", str(source_id), expected.value, previous.version.value
                )
            if previous.status is not SourceStatus.ACTIVE:
                raise InvariantViolation("knowledge_already_disabled")
            updated = replace(
                previous, version=previous.version.next(), status=SourceStatus.DISABLED
            )
            self._sources[source_id] = updated
            return updated

    def save_pack(self, pack: EvidencePack) -> None:
        with self.atomic():
            run = self.runtime.get_run(pack.workspace_id, pack.run_id)
            if (
                pack.id in self._packs
                or pack.query.workspace_id != pack.workspace_id
                or len(self.packs(pack.workspace_id, pack.run_id)) >= 5
                or pack.context_chars > pack.query.max_context_chars
                or run.status is not AgentRunStatus.RUNNING
                or run.working_state.invocation_pending
                or not run.created_at <= pack.created_at < run.deadline
            ):
                raise InvariantViolation("knowledge_pack_identity_or_limit")
            scope = run.definition_version.knowledge_scope
            if (
                not scope.source_ids
                or not set(pack.query.source_filters) <= set(scope.source_ids)
                or not set(pack.query.trust_filters) <= set(scope.trust_classes)
            ):
                raise InvariantViolation("knowledge_pack_query_scope")
            seen: set[tuple[KnowledgeSourceId, str]] = set()
            counts: dict[KnowledgeSourceId, int] = {}
            for candidate in pack.result.candidates:
                chunk = candidate.chunk
                source = self.source(pack.workspace_id, chunk.source_id)
                version = self.version(pack.workspace_id, chunk.source_id, chunk.source_version)
                if (
                    chunk.workspace_id != pack.workspace_id
                    or chunk.source_id not in scope.source_ids
                    or source.trust not in scope.trust_classes
                    or source.status is not SourceStatus.ACTIVE
                    or source.content_version != chunk.source_version
                    or source.id not in (pack.query.source_filters or scope.source_ids)
                    or source.trust not in (pack.query.trust_filters or scope.trust_classes)
                    or chunk not in self.chunks(pack.workspace_id, source.id, chunk.source_version)
                    or candidate.source_name != version.source.name
                    or candidate.trust != version.source.trust
                    or candidate.source_created_at != version.created_at
                ):
                    raise InvariantViolation("knowledge_pack_evidence_binding")
                key = (source.id, chunk.content_hash)
                counts[source.id] = counts.get(source.id, 0) + 1
                if (
                    key in seen
                    or counts[source.id] > pack.query.max_per_source
                    or candidate.score <= 0
                ):
                    raise InvariantViolation("knowledge_pack_duplicate_or_diversity")
                seen.add(key)
            self._packs[pack.id] = pack

    def pack(
        self, workspace_id: WorkspaceId, run_id: AgentRunId, pack_id: EvidencePackId
    ) -> EvidencePack:
        self.runtime.get_run(workspace_id, run_id)
        try:
            pack = self._packs[pack_id]
        except KeyError as error:
            raise EntityNotFound("EvidencePack", str(pack_id)) from error
        if pack.workspace_id != workspace_id:
            raise WorkspaceMismatch("EvidencePack", str(workspace_id), str(pack.workspace_id))
        if pack.run_id != run_id:
            raise InvariantViolation("knowledge_pack_run_binding")
        return pack

    def packs(self, workspace_id: WorkspaceId, run_id: AgentRunId) -> tuple[EvidencePack, ...]:
        self.runtime.get_run(workspace_id, run_id)
        return tuple(
            p for p in self._packs.values() if p.workspace_id == workspace_id and p.run_id == run_id
        )

    def append_event(self, event: Event) -> None:
        source = self.source(event.workspace_id, KnowledgeSourceId(event.subject_id))
        if (
            event.subject_type is not SubjectType.KNOWLEDGE_SOURCE
            or event.entity_version != source.version
            or any(e.id == event.id for e in self._events)
        ):
            raise InvariantViolation("knowledge_event_binding")
        self._events.append(event)

    def events(self, workspace_id: WorkspaceId) -> tuple[Event, ...]:
        self.runtime.domain.get_workspace(workspace_id)
        return tuple(e for e in self._events if e.workspace_id == workspace_id)
