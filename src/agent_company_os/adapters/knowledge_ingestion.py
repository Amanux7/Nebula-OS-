"""Pure bounded UTF-8 ingestion and deterministic non-overlapping chunks."""

import json

from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.knowledge import (
    IngestionLimits,
    KnowledgeFact,
    NormalizedContent,
    SourceType,
    bounded_text,
)


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvariantViolation("knowledge_duplicate_json_key")
        result[key] = value
    return result


class TextKnowledgeIngestor:
    def normalize(
        self,
        raw: bytes,
        source_type: SourceType,
        limits: IngestionLimits,
    ) -> NormalizedContent:
        if not isinstance(raw, bytes) or len(raw) > limits.source_bytes:
            raise InvariantViolation("knowledge_source_bytes")
        try:
            text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeError as error:
            raise InvariantViolation("knowledge_utf8") from error
        bounded_text(text, limits.normalized_chars)
        if source_type in (SourceType.TEXT, SourceType.MARKDOWN):
            return NormalizedContent(text)
        if source_type is not SourceType.STRUCTURED_FACTS:
            raise InvariantViolation("knowledge_source_type")
        try:
            data = json.loads(text, object_pairs_hook=unique_object)
        except (ValueError, RecursionError) as error:
            raise InvariantViolation("knowledge_json") from error
        if not isinstance(data, dict) or set(data) != {"company", "facts"}:
            raise InvariantViolation("knowledge_fact_schema")
        bounded_text(data["company"], 128)
        rows = data["facts"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= limits.facts:
            raise InvariantViolation("knowledge_fact_count")
        facts: list[KnowledgeFact] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"key", "value"}:
                raise InvariantViolation("knowledge_fact_schema")
            facts.append(KnowledgeFact(row["key"], row["value"]))
        if len(set(facts)) != len(facts):
            raise InvariantViolation("knowledge_duplicate_fact")
        normalized = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        bounded_text(normalized, limits.normalized_chars)
        return NormalizedContent(normalized, data["company"], tuple(facts))
