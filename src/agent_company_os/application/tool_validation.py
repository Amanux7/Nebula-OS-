"""Strict tool JSON schemas with byte, field and collection limits."""

import json

from agent_company_os.domain.agent import Fact
from agent_company_os.domain.tools import (
    CompanyLookupInput,
    ExecutorKind,
    FixtureMessageInput,
    SourceLookupInput,
    ToolError,
    ToolFailure,
    ToolInput,
    ToolOutput,
    ToolVersion,
)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def bounded_json(raw: str, maximum: int, code: ToolError) -> object:
    try:
        if not isinstance(raw, str) or len(raw) > maximum or len(raw.encode("utf-8")) > maximum:
            raise ToolFailure(code)
        value: object = json.loads(raw, object_pairs_hook=_pairs)
        return value
    except (ValueError, RecursionError, UnicodeError) as error:
        raise ToolFailure(code) from error


def _object(value: object, keys: set[str], code: ToolError) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ToolFailure(code)
    return {str(key): item for key, item in value.items()}


def _text(value: object, maximum: int, code: ToolError) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ToolFailure(code)
    try:
        value.encode("utf-8")
    except UnicodeError as error:
        raise ToolFailure(code) from error
    return value


def validate_input(raw: str, version: ToolVersion) -> ToolInput:
    code = ToolError.VALIDATION_ERROR
    value = bounded_json(raw, version.max_input_bytes, code)
    if version.executor_kind is ExecutorKind.SEND_FIXTURE_MESSAGE:
        item = _object(value, {"destination", "message"}, code)
        return FixtureMessageInput(
            _text(item["destination"], 128, code), _text(item["message"], 512, code)
        )
    if version.executor_kind is ExecutorKind.COMPANY_LOOKUP:
        item = _object(value, {"company_name"}, code)
        return CompanyLookupInput(_text(item["company_name"], 128, code))
    item = _object(value, {"source_id", "keys"}, code)
    keys = item["keys"]
    if not isinstance(keys, list) or not 1 <= len(keys) <= 10:
        raise ToolFailure(code)
    parsed = tuple(_text(key, 128, code) for key in keys)
    if len(set(parsed)) != len(parsed):
        raise ToolFailure(code)
    return SourceLookupInput(_text(item["source_id"], 128, code), parsed)


def input_json(value: ToolInput) -> str:
    fields: dict[str, object]
    if isinstance(value, CompanyLookupInput):
        fields = {"company_name": value.company_name}
    elif isinstance(value, FixtureMessageInput):
        fields = {"destination": value.destination, "message": value.message}
    else:
        fields = {"source_id": value.source_id, "keys": list(value.keys)}
    return json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_output(raw: str, version: ToolVersion, request: ToolInput) -> ToolOutput:
    code = ToolError.MALFORMED_OUTPUT
    if not isinstance(raw, str):
        raise ToolFailure(code)
    try:
        if (
            len(raw) > version.max_output_bytes
            or len(raw.encode("utf-8")) > version.max_output_bytes
        ):
            raise ToolFailure(ToolError.OUTPUT_TOO_LARGE)
    except UnicodeError as error:
        raise ToolFailure(code) from error
    value = bounded_json(raw, version.max_output_bytes, code)
    item = _object(value, {"schema_version", "subject", "facts", "notes"}, code)
    if type(item["schema_version"]) is not int or item["schema_version"] != 1:
        raise ToolFailure(code)
    subject = _text(item["subject"], 128, code)
    expected = (
        request.company_name
        if isinstance(request, CompanyLookupInput)
        else request.destination
        if isinstance(request, FixtureMessageInput)
        else request.source_id
    )
    if subject != expected:
        raise ToolFailure(code)
    rows = item["facts"]
    if isinstance(request, FixtureMessageInput) and rows != []:
        raise ToolFailure(code)  # Delivery receipts cannot invent factual grounding.
    if not isinstance(rows, list) or len(rows) > 10:
        raise ToolFailure(code)
    facts = []
    for row in rows:
        fields = _object(row, {"key", "value", "source_id"}, code)
        fact = Fact(
            _text(fields["key"], 128, code),
            _text(fields["value"], 512, code),
            _text(fields["source_id"], 128, code),
        )
        if fact.source_id.startswith(("tool_receipt:", "knowledge:")):
            raise ToolFailure(code)
        if isinstance(request, SourceLookupInput) and (
            fact.key not in request.keys or fact.source_id != request.source_id
        ):
            raise ToolFailure(code)
        facts.append(fact)
    if len(set(facts)) != len(facts):
        raise ToolFailure(code)
    notes = item["notes"]
    if not isinstance(notes, str) or len(notes) > 512:
        raise ToolFailure(code)
    if notes:
        _text(notes, 512, code)
    return ToolOutput(subject, tuple(facts), notes)
