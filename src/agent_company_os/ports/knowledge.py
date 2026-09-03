"""Used knowledge boundaries; no vector store, tool registry or memory dependency."""

from contextlib import AbstractContextManager
from typing import Protocol

from agent_company_os.domain.agent import AgentRun, AgentRunId, Fact
from agent_company_os.domain.events import Event
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.knowledge import (
    EvidenceCandidate,
    EvidencePack,
    EvidencePackId,
    IngestionLimits,
    KnowledgeChunk,
    KnowledgeQuery,
    KnowledgeSource,
    KnowledgeSourceId,
    KnowledgeSourceVersion,
    NormalizedContent,
    RetrievalResult,
    SourceType,
)
from agent_company_os.ports.runtime_store import RuntimeStore


class KnowledgeIngestor(Protocol):
    def normalize(
        self, raw: bytes, source_type: SourceType, limits: IngestionLimits
    ) -> NormalizedContent: ...


class KnowledgeRetriever(Protocol):
    def retrieve(
        self, query: KnowledgeQuery, eligible: tuple[EvidenceCandidate, ...]
    ) -> RetrievalResult: ...


class KnowledgeStore(Protocol):
    runtime: RuntimeStore

    def atomic(self) -> AbstractContextManager[None]: ...
    def source(
        self, workspace_id: WorkspaceId, source_id: KnowledgeSourceId
    ) -> KnowledgeSource: ...
    def version(
        self, workspace_id: WorkspaceId, source_id: KnowledgeSourceId, version: Version
    ) -> KnowledgeSourceVersion: ...
    def chunks(
        self, workspace_id: WorkspaceId, source_id: KnowledgeSourceId, version: Version
    ) -> tuple[KnowledgeChunk, ...]: ...
    def publish(
        self,
        version: KnowledgeSourceVersion,
        chunks: tuple[KnowledgeChunk, ...],
        expected: Version | None,
    ) -> None: ...
    def disable(
        self, workspace_id: WorkspaceId, source_id: KnowledgeSourceId, expected: Version
    ) -> KnowledgeSource: ...
    def save_pack(self, pack: EvidencePack) -> None: ...
    def pack(
        self, workspace_id: WorkspaceId, run_id: AgentRunId, pack_id: EvidencePackId
    ) -> EvidencePack: ...
    def packs(self, workspace_id: WorkspaceId, run_id: AgentRunId) -> tuple[EvidencePack, ...]: ...
    def append_event(self, event: Event) -> None: ...


class KnowledgeRuntimePort(Protocol):
    def active_pack(self, run: AgentRun) -> EvidencePack | None: ...
    def evidence(self, run: AgentRun) -> tuple[Fact, ...]: ...
