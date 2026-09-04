"""Small deterministic exact-subject lexical memory retriever."""

import re

from agent_company_os.domain.memory import (
    MemoryEntry,
    MemoryHit,
    MemoryQuery,
    MemoryRetrievalResult,
)


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


class LexicalMemoryRetriever:
    version = "exact-subject-lexical-v1"

    def retrieve(
        self, query: MemoryQuery, eligible: tuple[MemoryEntry, ...]
    ) -> MemoryRetrievalResult:
        query_terms = _tokens(query.text)
        subject = " ".join(query.subject.casefold().split())
        ranked: list[MemoryHit] = []
        for entry in eligible:
            if " ".join(entry.subject.casefold().split()) != subject:
                continue
            terms = _tokens(entry.content)
            overlap = len(query_terms & terms) / max(len(query_terms), 1)
            ranked.append(MemoryHit(entry, round(1.0 + overlap, 6)))
        ranked.sort(
            key=lambda hit: (
                -hit.score,
                -hit.entry.reviewed_at.timestamp(),
                str(hit.entry.id),
            )
        )
        selected: list[MemoryHit] = []
        used = 0
        for hit in ranked:
            size = len(hit.entry.content) + len(hit.entry.subject) + 128
            if used + size > query.max_context_chars:
                continue
            selected.append(hit)
            used += size
            if len(selected) == query.top_k:
                break
        return MemoryRetrievalResult(tuple(selected), self.version)
