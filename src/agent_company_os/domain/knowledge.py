"""Versioned approved knowledge, not learned memory or executable instructions."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from urllib.parse import quote

from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.ids import OpaqueId, Version, WorkspaceId
from agent_company_os.domain.validation import require_utc

if TYPE_CHECKING:
    from agent_company_os.domain.agent import AgentRunId


class KnowledgeSourceId(OpaqueId):
    pass


class KnowledgeChunkId(OpaqueId):
    pass


class EvidencePackId(OpaqueId):
    pass


class SourceType(StrEnum):
    TEXT = "text"
    MARKDOWN = "markdown"
    STRUCTURED_FACTS = "structured_facts"


class TrustClass(StrEnum):
    AUTHORITATIVE = "authoritative"
    APPROVED_INTERNAL = "approved_internal"
    UNVERIFIED_EXTERNAL = "unverified_external"


class SourceStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


def bounded_text(value: str, maximum: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise InvariantViolation("knowledge_text_bound")
    if any(ord(c) < 32 and c not in "\n\t" or 127 <= ord(c) < 160 for c in value):
        raise InvariantViolation("knowledge_control_character")
    try:
        value.encode("utf-8")
    except UnicodeError as error:
        raise InvariantViolation("knowledge_utf8") from error


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class KnowledgeScope:
    source_ids: tuple[KnowledgeSourceId, ...] = ()
    trust_classes: tuple[TrustClass, ...] = (
        TrustClass.AUTHORITATIVE,
        TrustClass.APPROVED_INTERNAL,
    )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_ids, tuple)
            or len(self.source_ids) > 20
            or len(set(self.source_ids)) != len(self.source_ids)
            or any(not isinstance(item, KnowledgeSourceId) for item in self.source_ids)
            or not isinstance(self.trust_classes, tuple)
            or not self.trust_classes
            or len(set(self.trust_classes)) != len(self.trust_classes)
            or any(not isinstance(item, TrustClass) for item in self.trust_classes)
        ):
            raise InvariantViolation("knowledge_scope_schema")


@dataclass(frozen=True)
class IngestionLimits:
    source_bytes: int = 32768
    normalized_chars: int = 16000
    facts: int = 50
    chunk_chars: int = 800
    chunks: int = 64

    def __post_init__(self) -> None:
        for value, maximum in (
            (self.source_bytes, 131072),
            (self.normalized_chars, 64000),
            (self.facts, 100),
            (self.chunk_chars, 2000),
            (self.chunks, 128),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise InvariantViolation("knowledge_ingestion_limit")


@dataclass(frozen=True)
class KnowledgeFact:
    key: str
    value: str

    def __post_init__(self) -> None:
        bounded_text(self.key, 128)
        bounded_text(self.value, 512)


@dataclass(frozen=True)
class NormalizedContent:
    text: str
    company: str | None = None
    facts: tuple[KnowledgeFact, ...] = ()
    algorithm: str = "utf8-lf-v1"

    def __post_init__(self) -> None:
        bounded_text(self.text, 64000)
        if (
            self.algorithm != "utf8-lf-v1"
            or "\r" in self.text
            or not isinstance(self.facts, tuple)
            or len(self.facts) > 100
            or any(not isinstance(f, KnowledgeFact) for f in self.facts)
            or (self.company is not None) != bool(self.facts)
        ):
            raise InvariantViolation("knowledge_normalized_schema")
        if self.company is not None:
            bounded_text(self.company, 128)
            expected = json.dumps(
                {
                    "company": self.company,
                    "facts": [{"key": f.key, "value": f.value} for f in self.facts],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if self.text != expected or len(set(self.facts)) != len(self.facts):
                raise InvariantViolation("knowledge_structured_content_binding")


@dataclass(frozen=True)
class KnowledgeSource:
    id: KnowledgeSourceId
    workspace_id: WorkspaceId
    name: str
    source_type: SourceType
    trust: TrustClass
    created_at: datetime
    version: Version = Version(1)
    content_version: Version = Version(1)
    status: SourceStatus = SourceStatus.ACTIVE

    def __post_init__(self) -> None:
        bounded_text(self.name, 128)
        require_utc(self.created_at, "created_at")
        if not isinstance(self.source_type, SourceType) or not isinstance(self.trust, TrustClass):
            raise InvariantViolation("knowledge_source_schema")


@dataclass(frozen=True)
class KnowledgeSourceVersion:
    source: KnowledgeSource
    content: NormalizedContent
    content_hash: str
    created_at: datetime
    limits: IngestionLimits
    chunking_algorithm: str = "paragraph-or-fact-v1"
    schema_version: int = 1

    def __post_init__(self) -> None:
        require_utc(self.created_at, "created_at")
        bounded_text(self.content.text, self.limits.normalized_chars)
        if (
            self.content_hash != digest(self.content.text)
            or self.schema_version != 1
            or self.chunking_algorithm != "paragraph-or-fact-v1"
            or len(self.content.facts) > self.limits.facts
            or (self.source.source_type is SourceType.STRUCTURED_FACTS) != bool(self.content.facts)
            or self.created_at < self.source.created_at
        ):
            raise InvariantViolation("knowledge_content_hash_or_schema")


@dataclass(frozen=True)
class KnowledgeChunk:
    id: KnowledgeChunkId
    workspace_id: WorkspaceId
    source_id: KnowledgeSourceId
    source_version: Version
    ordinal: int
    text: str
    content_hash: str
    fact: KnowledgeFact | None = None

    def __post_init__(self) -> None:
        bounded_text(self.text, 2000)
        if self.content_hash != digest(self.text) or self.ordinal < 0:
            raise InvariantViolation("knowledge_chunk_integrity")

    @property
    def reference(self) -> str:
        return "knowledge:" + ":".join(
            quote(str(value), safe="")
            for value in (self.source_id, self.source_version.value, self.id)
        )


@dataclass(frozen=True)
class KnowledgeQuery:
    workspace_id: WorkspaceId
    text: str
    source_filters: tuple[KnowledgeSourceId, ...] = ()
    trust_filters: tuple[TrustClass, ...] = ()
    top_k: int = 5
    max_context_chars: int = 4000
    max_per_source: int = 2

    def __post_init__(self) -> None:
        bounded_text(self.text, 512)
        for value, maximum in (
            (self.top_k, 10),
            (self.max_context_chars, 12000),
            (self.max_per_source, 5),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise InvariantViolation("knowledge_query_limit")
        for items, kind, maximum in (
            (self.source_filters, KnowledgeSourceId, 20),
            (self.trust_filters, TrustClass, 3),
        ):
            if (
                not isinstance(items, tuple)
                or len(items) > maximum
                or len(set(items)) != len(items)
                or any(not isinstance(i, kind) for i in items)
            ):
                raise InvariantViolation("knowledge_query_filters")


@dataclass(frozen=True)
class EvidenceCandidate:
    chunk: KnowledgeChunk
    source_name: str
    trust: TrustClass
    source_created_at: datetime
    score: float = 0.0

    def __post_init__(self) -> None:
        bounded_text(self.source_name, 128)
        require_utc(self.source_created_at, "source_created_at")
        if (
            not isinstance(self.trust, TrustClass)
            or not math.isfinite(self.score)
            or not 0 <= self.score <= 1
        ):
            raise InvariantViolation("knowledge_candidate_schema")

    @property
    def context_chars(self) -> int:
        # Include duplicate typed-fact representation and all descriptive metadata.
        return len(json.dumps(candidate_data(self), ensure_ascii=False, sort_keys=True))


@dataclass(frozen=True)
class RetrievalResult:
    candidates: tuple[EvidenceCandidate, ...]
    candidate_count: int
    truncated: bool
    strategy: str = "lexical-overlap"
    strategy_version: int = 1

    def __post_init__(self) -> None:
        if (
            not isinstance(self.candidates, tuple)
            or len(self.candidates) > 10
            or any(not isinstance(c, EvidenceCandidate) for c in self.candidates)
            or type(self.candidate_count) is not int
            or not len(self.candidates) <= self.candidate_count <= 2560
            or type(self.truncated) is not bool
            or self.strategy != "lexical-overlap"
            or self.strategy_version != 1
        ):
            raise InvariantViolation("knowledge_result_schema")


@dataclass(frozen=True)
class EvidencePack:
    id: EvidencePackId
    workspace_id: WorkspaceId
    run_id: AgentRunId
    query: KnowledgeQuery
    result: RetrievalResult
    created_at: datetime
    schema_version: int = 1

    def __post_init__(self) -> None:
        require_utc(self.created_at, "created_at")
        if (
            self.schema_version != 1
            or self.workspace_id != self.query.workspace_id
            or len(self.result.candidates) > self.query.top_k
            or any(c.chunk.workspace_id != self.workspace_id for c in self.result.candidates)
        ):
            raise InvariantViolation("knowledge_pack_schema")

    @property
    def context_chars(self) -> int:
        return len(json.dumps(serialize_pack(self), ensure_ascii=False, sort_keys=True))


def candidate_data(item: EvidenceCandidate) -> dict[str, object]:
    chunk = item.chunk
    return {
        "source_id": str(chunk.source_id),
        "source_version": chunk.source_version.value,
        "chunk_id": str(chunk.id),
        "ordinal": chunk.ordinal,
        "text": chunk.text,
        "hash": chunk.content_hash,
        "reference": chunk.reference,
        "fact": {"key": chunk.fact.key, "value": chunk.fact.value} if chunk.fact else None,
        "source_name": item.source_name,
        "trust": item.trust.value,
        "score": item.score,
        "source_created_at": item.source_created_at.isoformat(),
        "instruction_trust": "untrusted_source_data",
    }


def serialize_pack(pack: EvidencePack) -> dict[str, object]:
    return {
        "schema_version": pack.schema_version,
        "id": str(pack.id),
        "workspace_id": str(pack.workspace_id),
        "run_id": str(pack.run_id),
        "created_at": pack.created_at.isoformat(),
        "query": {
            "text": pack.query.text,
            "source_filters": [str(i) for i in pack.query.source_filters],
            "trust_filters": [i.value for i in pack.query.trust_filters],
            "top_k": pack.query.top_k,
            "max_context_chars": pack.query.max_context_chars,
            "max_per_source": pack.query.max_per_source,
        },
        "strategy": pack.result.strategy,
        "strategy_version": pack.result.strategy_version,
        "candidate_count": pack.result.candidate_count,
        "truncated": pack.result.truncated,
        "candidates": [candidate_data(item) for item in pack.result.candidates],
    }
