"""Boundaries used by governed memory; no vector or model dependency."""

from contextlib import AbstractContextManager
from typing import Protocol

from agent_company_os.domain.agent import AgentRun, AgentRunId
from agent_company_os.domain.events import Event
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.memory import (
    MemoryCandidate,
    MemoryCandidateId,
    MemoryContextPack,
    MemoryContextPackId,
    MemoryEntry,
    MemoryEntryId,
    MemoryQuery,
    MemoryRetrievalResult,
)
from agent_company_os.ports.runtime_store import RuntimeStore


class MemoryRetriever(Protocol):
    def retrieve(
        self, query: MemoryQuery, eligible: tuple[MemoryEntry, ...]
    ) -> MemoryRetrievalResult: ...


class MemoryStore(Protocol):
    runtime: RuntimeStore

    def atomic(self) -> AbstractContextManager[None]: ...
    def candidate(
        self, workspace_id: WorkspaceId, candidate_id: MemoryCandidateId
    ) -> MemoryCandidate: ...
    def candidates(self, workspace_id: WorkspaceId) -> tuple[MemoryCandidate, ...]: ...
    def add_candidate(self, candidate: MemoryCandidate) -> MemoryCandidate: ...
    def save_candidate(self, candidate: MemoryCandidate, expected: Version) -> None: ...
    def entry(self, workspace_id: WorkspaceId, entry_id: MemoryEntryId) -> MemoryEntry: ...
    def entries(self, workspace_id: WorkspaceId) -> tuple[MemoryEntry, ...]: ...
    def add_entry(self, entry: MemoryEntry) -> None: ...
    def save_entry(self, entry: MemoryEntry, expected: Version) -> None: ...
    def save_pack(self, pack: MemoryContextPack) -> None: ...
    def pack(
        self, workspace_id: WorkspaceId, run_id: AgentRunId, pack_id: MemoryContextPackId
    ) -> MemoryContextPack: ...
    def packs(
        self, workspace_id: WorkspaceId, run_id: AgentRunId
    ) -> tuple[MemoryContextPack, ...]: ...
    def append_event(self, event: Event) -> None: ...


class MemoryRuntimePort(Protocol):
    def active_pack(self, run: AgentRun) -> MemoryContextPack | None: ...
