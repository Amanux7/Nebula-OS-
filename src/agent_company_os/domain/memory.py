"""Governed retained experience; separate from knowledge and working state."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from agent_company_os.domain.errors import InvalidStateTransition, InvariantViolation
from agent_company_os.domain.ids import OpaqueId, Version, WorkspaceId
from agent_company_os.domain.validation import clean_required_text, require_utc

if TYPE_CHECKING:
    from agent_company_os.domain.agent import AgentRunId


class MemoryCandidateId(OpaqueId):
    pass


class MemoryEntryId(OpaqueId):
    pass


class MemoryContextPackId(OpaqueId):
    pass


class MemoryType(StrEnum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


class MemoryAuthority(StrEnum):
    OBSERVED = "observed"
    STATED = "stated"
    INFERRED = "inferred"
    DERIVED = "derived"
    REVIEWED = "reviewed"


class MemorySensitivity(StrEnum):
    NORMAL = "normal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class MemoryScopeKind(StrEnum):
    WORKSPACE = "workspace"
    AGENT = "agent"
    USER = "user"
    CUSTOMER = "customer"
    TASK = "task"
    DOMAIN = "domain"


@dataclass(frozen=True)
class MemoryScope:
    kind: MemoryScopeKind
    key: str

    def __post_init__(self) -> None:
        clean_required_text(self.key, "memory_scope_key")
        if len(self.key) > 128 or self.kind is MemoryScopeKind.WORKSPACE and self.key != "*":
            raise InvariantViolation("memory_scope_bound")


@dataclass(frozen=True)
class MemoryAccessPolicy:
    scopes: tuple[MemoryScope, ...] = ()
    sensitivities: tuple[MemorySensitivity, ...] = (MemorySensitivity.NORMAL,)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scopes, tuple)
            or not isinstance(self.sensitivities, tuple)
            or len(self.scopes) > 20
            or len(set(self.scopes)) != len(self.scopes)
            or not self.sensitivities
            or len(set(self.sensitivities)) != len(self.sensitivities)
        ):
            raise InvariantViolation("memory_access_policy_bound")


class MemoryProvenanceKind(StrEnum):
    USER_STATEMENT = "user_statement"
    TOOL_RECEIPT = "tool_receipt"
    KNOWLEDGE_EVIDENCE = "knowledge_evidence"
    AGENT_OUTPUT = "agent_output"
    TASK_RESULT = "task_result"


@dataclass(frozen=True)
class MemoryProvenance:
    kind: MemoryProvenanceKind
    run_id: AgentRunId
    source_references: tuple[str, ...]
    authority: MemoryAuthority

    def __post_init__(self) -> None:
        if not self.source_references or len(self.source_references) > 10:
            raise InvariantViolation("memory_provenance_reference_bound")
        for reference in self.source_references:
            clean_required_text(reference, "memory_source_reference")
            if len(reference) > 256:
                raise InvariantViolation("memory_source_reference_bound")


class MemoryCandidateStatus(StrEnum):
    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    PROMOTED = "promoted"
    REJECTED = "rejected"


class MemoryEntryStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class MemoryCandidate:
    id: MemoryCandidateId
    workspace_id: WorkspaceId
    memory_type: MemoryType
    subject: str
    content: str
    scope: MemoryScope
    provenance: MemoryProvenance
    sensitivity: MemorySensitivity
    created_at: datetime
    claim_key: str | None = None
    claim_value: str | None = None
    expires_at: datetime | None = None
    status: MemoryCandidateStatus = MemoryCandidateStatus.PROPOSED
    version: Version = Version(1)
    policy_version: str = "review-only-memory-v1"
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        require_utc(self.created_at, "created_at")
        clean_required_text(self.subject, "memory_subject")
        clean_required_text(self.content, "memory_content")
        if len(self.subject) > 128 or len(self.content) > 1000:
            raise InvariantViolation("memory_content_bound")
        if (self.claim_key is None) != (self.claim_value is None):
            raise InvariantViolation("memory_claim_pair")
        for value in (self.claim_key, self.claim_value):
            if value is not None:
                clean_required_text(value, "memory_claim")
                if len(value) > 256:
                    raise InvariantViolation("memory_claim_bound")
        if self.expires_at is not None:
            require_utc(self.expires_at, "expires_at")
            if self.expires_at <= self.created_at:
                raise InvariantViolation("memory_expiry_after_creation")
        if (self.status is MemoryCandidateStatus.REJECTED) != bool(self.rejection_reason):
            raise InvariantViolation("memory_candidate_rejection_reason")

    @property
    def duplicate_key(self) -> tuple[object, ...]:
        def normalize(value: str) -> str:
            return " ".join(value.casefold().split())

        return (
            self.workspace_id,
            self.memory_type,
            normalize(self.subject),
            normalize(self.content),
            self.scope,
            self.claim_key.casefold() if self.claim_key else None,
            self.claim_value.casefold() if self.claim_value else None,
        )

    def review(self) -> MemoryCandidate:
        if self.status is not MemoryCandidateStatus.PROPOSED:
            raise InvalidStateTransition("MemoryCandidate", str(self.id), self.status, "review")
        return replace(self, status=MemoryCandidateStatus.UNDER_REVIEW, version=self.version.next())

    def reject(self, reason: str) -> MemoryCandidate:
        if self.status not in {MemoryCandidateStatus.PROPOSED, MemoryCandidateStatus.UNDER_REVIEW}:
            raise InvalidStateTransition("MemoryCandidate", str(self.id), self.status, "reject")
        clean_required_text(reason, "memory_rejection_reason")
        return replace(
            self,
            status=MemoryCandidateStatus.REJECTED,
            rejection_reason=reason[:256],
            version=self.version.next(),
        )

    def promote(self) -> MemoryCandidate:
        if self.status is not MemoryCandidateStatus.UNDER_REVIEW:
            raise InvalidStateTransition("MemoryCandidate", str(self.id), self.status, "promote")
        return replace(self, status=MemoryCandidateStatus.PROMOTED, version=self.version.next())


@dataclass(frozen=True)
class MemoryEntry:
    id: MemoryEntryId
    candidate: MemoryCandidate
    reviewed_by: str
    reviewed_at: datetime
    status: MemoryEntryStatus = MemoryEntryStatus.ACTIVE
    version: Version = Version(1)
    supersedes_id: MemoryEntryId | None = None
    ended_at: datetime | None = None
    status_reason: str | None = None

    def __post_init__(self) -> None:
        require_utc(self.reviewed_at, "reviewed_at")
        clean_required_text(self.reviewed_by, "memory_reviewer")
        if (
            len(self.reviewed_by) > 128
            or self.candidate.status is not MemoryCandidateStatus.PROMOTED
        ):
            raise InvariantViolation("memory_entry_review_binding")
        inactive = self.status is not MemoryEntryStatus.ACTIVE
        if inactive != (self.ended_at is not None) or inactive != bool(self.status_reason):
            raise InvariantViolation("memory_entry_terminal_metadata")

    @property
    def workspace_id(self) -> WorkspaceId:
        return self.candidate.workspace_id

    @property
    def memory_type(self) -> MemoryType:
        return self.candidate.memory_type

    @property
    def subject(self) -> str:
        return self.candidate.subject

    @property
    def content(self) -> str:
        return self.candidate.content

    @property
    def scope(self) -> MemoryScope:
        return self.candidate.scope

    @property
    def sensitivity(self) -> MemorySensitivity:
        return self.candidate.sensitivity

    @property
    def expires_at(self) -> datetime | None:
        return self.candidate.expires_at

    def is_expired(self, at: datetime) -> bool:
        require_utc(at, "at")
        return self.expires_at is not None and self.expires_at <= at

    def end(self, status: MemoryEntryStatus, at: datetime, reason: str) -> MemoryEntry:
        if self.status is not MemoryEntryStatus.ACTIVE or status is MemoryEntryStatus.ACTIVE:
            raise InvalidStateTransition("MemoryEntry", str(self.id), self.status, status)
        require_utc(at, "at")
        clean_required_text(reason, "memory_status_reason")
        return replace(
            self,
            status=status,
            version=self.version.next(),
            ended_at=at,
            status_reason=reason[:256],
        )


class MemoryPolicyDecision(StrEnum):
    REJECT = "reject"
    REQUIRES_REVIEW = "requires_review"


@dataclass(frozen=True)
class MemoryPolicyResult:
    decision: MemoryPolicyDecision
    reason: str


class MemoryPolicy:
    """Conservative Stage 5 policy: detectable risks reject; all else needs review."""

    version = "review-only-memory-v1"
    _secret = re.compile(
        r"(?i)(api[_ -]?key|password|private[_ -]?key|bearer\s+[a-z0-9._-]+|access[_ -]?token)"
    )

    def evaluate(self, candidate: MemoryCandidate) -> MemoryPolicyResult:
        if self._secret.search(candidate.content):
            return MemoryPolicyResult(MemoryPolicyDecision.REJECT, "detectable_secret")
        if candidate.provenance.kind is MemoryProvenanceKind.KNOWLEDGE_EVIDENCE:
            return MemoryPolicyResult(MemoryPolicyDecision.REJECT, "knowledge_is_not_memory")
        if (
            candidate.provenance.kind is MemoryProvenanceKind.AGENT_OUTPUT
            or candidate.provenance.authority is MemoryAuthority.INFERRED
        ):
            return MemoryPolicyResult(MemoryPolicyDecision.REJECT, "unsupported_model_inference")
        return MemoryPolicyResult(MemoryPolicyDecision.REQUIRES_REVIEW, "human_review_required")


@dataclass(frozen=True)
class MemoryQuery:
    workspace_id: WorkspaceId
    subject: str
    text: str
    scopes: tuple[MemoryScope, ...]
    sensitivities: tuple[MemorySensitivity, ...] = (MemorySensitivity.NORMAL,)
    top_k: int = 5
    max_context_chars: int = 4000

    def __post_init__(self) -> None:
        clean_required_text(self.subject, "memory_query_subject")
        clean_required_text(self.text, "memory_query_text")
        if (
            len(self.subject) > 128
            or len(self.text) > 512
            or not self.scopes
            or len(self.scopes) > 20
            or len(set(self.scopes)) != len(self.scopes)
            or not self.sensitivities
            or not 1 <= self.top_k <= 10
            or not 1 <= self.max_context_chars <= 12000
        ):
            raise InvariantViolation("memory_query_bound")


@dataclass(frozen=True)
class MemoryHit:
    entry: MemoryEntry
    score: float
    conflicting_entry_ids: tuple[MemoryEntryId, ...] = ()
    conflicts_with_knowledge: bool = False


@dataclass(frozen=True)
class MemoryRetrievalResult:
    hits: tuple[MemoryHit, ...]
    strategy_version: str = "exact-subject-lexical-v1"


@dataclass(frozen=True)
class MemoryContextPack:
    id: MemoryContextPackId
    workspace_id: WorkspaceId
    run_id: AgentRunId
    query: MemoryQuery
    result: MemoryRetrievalResult
    created_at: datetime
    context_chars: int
    schema_version: int = 1

    def __post_init__(self) -> None:
        require_utc(self.created_at, "created_at")
        if (
            self.query.workspace_id != self.workspace_id
            or self.schema_version != 1
            or self.context_chars < 0
            or self.context_chars > self.query.max_context_chars
            or len(self.result.hits) > self.query.top_k
        ):
            raise InvariantViolation("memory_context_pack_bound")


def serialize_memory_pack(pack: MemoryContextPack) -> str:
    lines = []
    for hit in pack.result.hits:
        entry = hit.entry
        flags = []
        if hit.conflicts_with_knowledge:
            flags.append("conflicts_with_authoritative_knowledge")
        if hit.conflicting_entry_ids:
            flags.append("conflicts_with_memory")
        lines.append(
            " | ".join(
                (
                    "category=retained_memory",
                    f"entry={entry.id}",
                    f"type={entry.memory_type}",
                    f"authority={entry.candidate.provenance.authority}",
                    f"sensitivity={entry.sensitivity}",
                    f"subject={entry.subject}",
                    f"content={entry.content}",
                    f"flags={','.join(flags) or 'none'}",
                )
            )
        )
    return "\n".join(lines)


def serialize_candidate(candidate: MemoryCandidate) -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": str(candidate.id),
        "workspace_id": str(candidate.workspace_id),
        "memory_type": candidate.memory_type.value,
        "subject": candidate.subject,
        "content": candidate.content,
        "scope": {"kind": candidate.scope.kind.value, "key": candidate.scope.key},
        "provenance": {
            "kind": candidate.provenance.kind.value,
            "run_id": str(candidate.provenance.run_id),
            "source_references": list(candidate.provenance.source_references),
            "authority": candidate.provenance.authority.value,
        },
        "sensitivity": candidate.sensitivity.value,
        "created_at": candidate.created_at.isoformat(),
        "expires_at": candidate.expires_at.isoformat() if candidate.expires_at else None,
        "status": candidate.status.value,
        "version": candidate.version.value,
        "policy_version": candidate.policy_version,
        "rejection_reason": candidate.rejection_reason,
        "claim_key": candidate.claim_key,
        "claim_value": candidate.claim_value,
    }


def serialize_entry(entry: MemoryEntry) -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": str(entry.id),
        "candidate": serialize_candidate(entry.candidate),
        "reviewed_by": entry.reviewed_by,
        "reviewed_at": entry.reviewed_at.isoformat(),
        "status": entry.status.value,
        "version": entry.version.value,
        "supersedes_id": str(entry.supersedes_id) if entry.supersedes_id else None,
        "ended_at": entry.ended_at.isoformat() if entry.ended_at else None,
        "status_reason": entry.status_reason,
    }
