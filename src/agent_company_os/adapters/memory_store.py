"""In-process memory records sharing the runtime transaction boundary."""

from collections.abc import Iterator
from contextlib import contextmanager

from agent_company_os.domain.agent import AgentRunId, AgentRunStatus
from agent_company_os.domain.errors import (
    EntityNotFound,
    InvariantViolation,
    VersionConflict,
    WorkspaceMismatch,
)
from agent_company_os.domain.events import Event
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.memory import (
    MemoryCandidate,
    MemoryCandidateId,
    MemoryContextPack,
    MemoryContextPackId,
    MemoryEntry,
    MemoryEntryId,
    MemoryEntryStatus,
)
from agent_company_os.domain.transitions import SubjectType
from agent_company_os.ports.runtime_store import RuntimeStore


class InMemoryMemoryStore:
    def __init__(self, runtime: RuntimeStore) -> None:
        self.runtime = runtime
        self._candidates: dict[MemoryCandidateId, MemoryCandidate] = {}
        self._entries: dict[MemoryEntryId, MemoryEntry] = {}
        self._packs: dict[MemoryContextPackId, MemoryContextPack] = {}
        self._events: list[Event] = []

    @contextmanager
    def atomic(self) -> Iterator[None]:
        with self.runtime.atomic():
            snapshot = (
                self._candidates.copy(),
                self._entries.copy(),
                self._packs.copy(),
                self._events.copy(),
            )
            try:
                yield
            except BaseException:
                self._candidates, self._entries, self._packs, self._events = snapshot
                raise

    @staticmethod
    def _scope(expected: WorkspaceId, actual: WorkspaceId, subject: str) -> None:
        if expected != actual:
            raise WorkspaceMismatch(subject, str(expected), str(actual))

    def candidate(
        self, workspace_id: WorkspaceId, candidate_id: MemoryCandidateId
    ) -> MemoryCandidate:
        try:
            candidate = self._candidates[candidate_id]
        except KeyError as error:
            raise EntityNotFound("MemoryCandidate", str(candidate_id)) from error
        self._scope(workspace_id, candidate.workspace_id, "MemoryCandidate")
        return candidate

    def candidates(self, workspace_id: WorkspaceId) -> tuple[MemoryCandidate, ...]:
        self.runtime.domain.get_workspace(workspace_id)
        return tuple(c for c in self._candidates.values() if c.workspace_id == workspace_id)

    def add_candidate(self, candidate: MemoryCandidate) -> MemoryCandidate:
        with self.atomic():
            self.runtime.domain.get_workspace(candidate.workspace_id)
            duplicate = next(
                (
                    old
                    for old in self._candidates.values()
                    if old.duplicate_key == candidate.duplicate_key
                ),
                None,
            )
            if duplicate is not None:
                return duplicate
            if (
                candidate.id in self._candidates
                or len(self.candidates(candidate.workspace_id)) >= 200
            ):
                raise InvariantViolation("memory_candidate_identity_or_workspace_limit")
            self._candidates[candidate.id] = candidate
            return candidate

    def save_candidate(self, candidate: MemoryCandidate, expected: Version) -> None:
        with self.atomic():
            previous = self.candidate(candidate.workspace_id, candidate.id)
            if previous.version != expected:
                raise VersionConflict(
                    "MemoryCandidate", str(candidate.id), expected.value, previous.version.value
                )
            if (
                candidate.version != previous.version.next()
                or candidate.duplicate_key != previous.duplicate_key
            ):
                raise InvariantViolation("memory_candidate_mutation_contract")
            self._candidates[candidate.id] = candidate

    def entry(self, workspace_id: WorkspaceId, entry_id: MemoryEntryId) -> MemoryEntry:
        try:
            entry = self._entries[entry_id]
        except KeyError as error:
            raise EntityNotFound("MemoryEntry", str(entry_id)) from error
        self._scope(workspace_id, entry.workspace_id, "MemoryEntry")
        return entry

    def entries(self, workspace_id: WorkspaceId) -> tuple[MemoryEntry, ...]:
        self.runtime.domain.get_workspace(workspace_id)
        return tuple(e for e in self._entries.values() if e.workspace_id == workspace_id)

    def add_entry(self, entry: MemoryEntry) -> None:
        with self.atomic():
            candidate = self.candidate(entry.workspace_id, entry.candidate.id)
            entries = self.entries(entry.workspace_id)
            if (
                entry.id in self._entries
                or candidate != entry.candidate
                or any(old.candidate.id == candidate.id for old in entries)
                or len(entries) >= 200
                or sum(old.subject.casefold() == entry.subject.casefold() for old in entries) >= 20
            ):
                raise InvariantViolation("memory_entry_binding_or_limit")
            self._entries[entry.id] = entry

    def save_entry(self, entry: MemoryEntry, expected: Version) -> None:
        with self.atomic():
            previous = self.entry(entry.workspace_id, entry.id)
            if previous.version != expected:
                raise VersionConflict(
                    "MemoryEntry", str(entry.id), expected.value, previous.version.value
                )
            if (
                entry.version != previous.version.next()
                or entry.candidate != previous.candidate
                or entry.reviewed_by != previous.reviewed_by
                or entry.reviewed_at != previous.reviewed_at
                or entry.supersedes_id != previous.supersedes_id
            ):
                raise InvariantViolation("memory_entry_mutation_contract")
            self._entries[entry.id] = entry

    def save_pack(self, pack: MemoryContextPack) -> None:
        with self.atomic():
            run = self.runtime.get_run(pack.workspace_id, pack.run_id)
            access = run.definition_version.memory_access
            if (
                pack.id in self._packs
                or len(self.packs(pack.workspace_id, pack.run_id)) >= 5
                or run.status is not AgentRunStatus.RUNNING
                or run.working_state.invocation_pending
                or not run.created_at <= pack.created_at < run.deadline
                or not set(pack.query.scopes) <= set(access.scopes)
                or not set(pack.query.sensitivities) <= set(access.sensitivities)
            ):
                raise InvariantViolation("memory_pack_identity_scope_or_limit")
            for hit in pack.result.hits:
                entry = self.entry(pack.workspace_id, hit.entry.id)
                if (
                    entry != hit.entry
                    or entry.status is not MemoryEntryStatus.ACTIVE
                    or entry.is_expired(pack.created_at)
                    or entry.scope not in access.scopes
                    or entry.sensitivity not in access.sensitivities
                ):
                    raise InvariantViolation("memory_pack_entry_binding")
            self._packs[pack.id] = pack

    def pack(
        self, workspace_id: WorkspaceId, run_id: AgentRunId, pack_id: MemoryContextPackId
    ) -> MemoryContextPack:
        self.runtime.get_run(workspace_id, run_id)
        try:
            pack = self._packs[pack_id]
        except KeyError as error:
            raise EntityNotFound("MemoryContextPack", str(pack_id)) from error
        self._scope(workspace_id, pack.workspace_id, "MemoryContextPack")
        if pack.run_id != run_id:
            raise InvariantViolation("memory_pack_run_binding")
        return pack

    def packs(self, workspace_id: WorkspaceId, run_id: AgentRunId) -> tuple[MemoryContextPack, ...]:
        self.runtime.get_run(workspace_id, run_id)
        return tuple(
            p for p in self._packs.values() if p.workspace_id == workspace_id and p.run_id == run_id
        )

    def append_event(self, event: Event) -> None:
        entity: MemoryCandidate | MemoryEntry
        if event.subject_type is SubjectType.MEMORY_CANDIDATE:
            entity = self.candidate(event.workspace_id, MemoryCandidateId(event.subject_id))
        elif event.subject_type is SubjectType.MEMORY_ENTRY:
            entity = self.entry(event.workspace_id, MemoryEntryId(event.subject_id))
        else:
            raise InvariantViolation("memory_event_subject")
        if event.entity_version != entity.version or any(
            old.id == event.id for old in self._events
        ):
            raise InvariantViolation("memory_event_binding")
        self._events.append(event)

    def events(self, workspace_id: WorkspaceId) -> tuple[Event, ...]:
        self.runtime.domain.get_workspace(workspace_id)
        return tuple(event for event in self._events if event.workspace_id == workspace_id)
