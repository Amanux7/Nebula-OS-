"""Small corpus baseline. Ranking is relevance, not authority or freshness."""

import re
from dataclasses import replace

from agent_company_os.domain.knowledge import EvidenceCandidate, KnowledgeQuery, RetrievalResult


class LexicalKnowledgeRetriever:
    def retrieve(
        self,
        query: KnowledgeQuery,
        eligible: tuple[EvidenceCandidate, ...],
    ) -> RetrievalResult:
        tokens = set(re.findall(r"\w+", query.text.casefold().replace("_", " ")))
        ranked: list[EvidenceCandidate] = []
        for item in eligible:
            terms = set(re.findall(r"\w+", item.chunk.text.casefold().replace("_", " ")))
            overlap = tokens & terms
            if overlap:
                ranked.append(replace(item, score=len(overlap) / len(tokens)))
        ranked.sort(key=lambda i: (-i.score, str(i.chunk.source_id), i.chunk.ordinal))
        chosen: list[EvidenceCandidate] = []
        seen: set[tuple[str, str]] = set()
        counts: dict[str, int] = {}
        size = 0
        for item in ranked:
            source = str(item.chunk.source_id)
            key = (source, item.chunk.content_hash)
            if (
                key in seen
                or counts.get(source, 0) >= query.max_per_source
                or len(chosen) >= query.top_k
                or size + item.context_chars > query.max_context_chars
            ):
                continue
            chosen.append(item)
            seen.add(key)
            counts[source] = counts.get(source, 0) + 1
            size += item.context_chars
        return RetrievalResult(tuple(chosen), len(ranked), len(chosen) < len(ranked))
