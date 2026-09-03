"""Deterministic versioned chunk projection from normalized canonical content."""

import json
import re

from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.knowledge import (
    KnowledgeChunk,
    KnowledgeChunkId,
    KnowledgeFact,
    KnowledgeSourceVersion,
    bounded_text,
    digest,
)


def chunk_content(version: KnowledgeSourceVersion) -> tuple[KnowledgeChunk, ...]:
    content, limit = version.content, version.limits.chunk_chars
    parts: list[tuple[str, KnowledgeFact | None]] = []
    if content.facts:
        parts = [(f"{content.company}\n{fact.key}: {fact.value}", fact) for fact in content.facts]
    else:
        # Prefer paragraph boundaries. Split long paragraphs at whitespace, then hard-cut
        # unbroken strings. Content is never executed; no overlap or semantic rewriting.
        for paragraph in re.split(r"\n[ \t]*\n", content.text):
            remaining = paragraph.strip()
            while remaining:
                end = min(limit, len(remaining))
                if end < len(remaining):
                    split = max(remaining.rfind(" ", 0, end), remaining.rfind("\n", 0, end))
                    if split > 0:
                        end = split
                part = remaining[:end].strip()
                if part:
                    parts.append((part, None))
                remaining = remaining[end:].strip()
                if len(parts) > version.limits.chunks:
                    raise InvariantViolation("knowledge_chunk_count")
    if not parts or len(parts) > version.limits.chunks:
        raise InvariantViolation("knowledge_chunk_count")
    result: list[KnowledgeChunk] = []
    source = version.source
    for ordinal, (text, fact) in enumerate(parts):
        bounded_text(text, limit)
        content_hash = digest(text)
        identity = json.dumps(
            [
                str(source.workspace_id),
                str(source.id),
                source.content_version.value,
                version.chunking_algorithm,
                limit,
                ordinal,
                content_hash,
            ]
        )
        result.append(
            KnowledgeChunk(
                KnowledgeChunkId(digest(identity)),
                source.workspace_id,
                source.id,
                source.content_version,
                ordinal,
                text,
                content_hash,
                fact,
            )
        )
    return tuple(result)
