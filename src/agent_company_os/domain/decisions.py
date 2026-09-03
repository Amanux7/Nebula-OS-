"""Strict, size-bounded decision parsing and extractive grounding validation."""

import json
from dataclasses import dataclass

from agent_company_os.domain.agent import (
    ActionId,
    ActionType,
    AgentRunId,
    Fact,
    ResearchBrief,
    SuppliedContext,
)
from agent_company_os.domain.ids import WorkspaceId
from agent_company_os.domain.tools import ToolId


class ModelFailure(Exception):
    """Categorized failures; raw provider messages are never copied into audit."""

    def __init__(self, code: str) -> None:
        if code not in {
            "schema_violation",
            "unsupported_schema_version",
            "empty_response",
            "response_too_large",
            "malformed_output",
            "unauthorized_action",
            "unsupported_completion",
            "ungrounded_fact",
            "context_overflow",
            "autonomy_denied",
            "unsupported_context_request",
            "model_timeout",
            "provider_unavailable",
            "rate_limited",
            "model_refused",
            "version_conflict",
            "deadline_exceeded",
            "tool_budget_exceeded",
        }:
            code = "provider_unavailable"
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Respond:
    message: str


@dataclass(frozen=True)
class RequestMoreContext:
    missing_fields: tuple[str, ...]


@dataclass(frozen=True)
class CompleteTask:
    findings: tuple[Fact, ...]
    gaps: tuple[str, ...]


@dataclass(frozen=True)
class CallTool:
    tool_id: ToolId
    arguments_json: str


type DecisionPayload = Respond | RequestMoreContext | CompleteTask | CallTool


@dataclass(frozen=True)
class ModelDecision:
    action_type: ActionType
    payload: DecisionPayload
    schema_version: int = 1


@dataclass(frozen=True)
class Action:
    id: ActionId
    run_id: AgentRunId
    workspace_id: WorkspaceId
    decision: ModelDecision
    iteration: int
    schema_version: int = 1


def _object(value: object, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ModelFailure("schema_violation")
    return {str(key): item for key, item in value.items()}


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1000:
        raise ModelFailure("schema_violation")
    return value


def _texts(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 50:
        raise ModelFailure("schema_violation")
    result = tuple(_text(item) for item in value)
    if len(set(result)) != len(result):
        raise ModelFailure("schema_violation")
    return result


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ModelFailure("schema_violation")
        result[key] = value
    return result


def parse_decision(raw: str, max_chars: int) -> ModelDecision:
    if not isinstance(raw, str) or not raw.strip():
        raise ModelFailure("empty_response")
    if len(raw) > max_chars:
        raise ModelFailure("response_too_large")
    try:
        decoded: object = json.loads(raw, object_pairs_hook=_no_duplicate_keys)
    except (ValueError, RecursionError) as error:
        raise ModelFailure("malformed_output") from error
    item = _object(decoded, {"schema_version", "action_type", "payload"})
    if type(item["schema_version"]) is not int or item["schema_version"] != 1:
        raise ModelFailure("unsupported_schema_version")
    try:
        kind = ActionType(_text(item["action_type"]))
    except ValueError as error:
        raise ModelFailure("unauthorized_action") from error
    payload: DecisionPayload
    if kind is ActionType.CALL_TOOL:
        content = _object(item["payload"], {"tool_id", "arguments"})
        if not isinstance(content["arguments"], dict):
            raise ModelFailure("schema_violation")
        payload = CallTool(
            ToolId(_text(content["tool_id"])),
            json.dumps(content["arguments"], sort_keys=True, ensure_ascii=False),
        )
    elif kind is ActionType.RESPOND:
        content = _object(item["payload"], {"message"})
        payload = Respond(_text(content["message"]))
    elif kind is ActionType.REQUEST_MORE_CONTEXT:
        content = _object(item["payload"], {"missing_fields"})
        missing = _texts(content["missing_fields"])
        if not missing:
            raise ModelFailure("schema_violation")
        payload = RequestMoreContext(missing)
    else:
        content = _object(item["payload"], {"findings", "gaps"})
        findings = content["findings"]
        if not isinstance(findings, list) or not 1 <= len(findings) <= 50:
            raise ModelFailure("schema_violation")
        facts = []
        for finding in findings:
            fields = _object(finding, {"key", "value", "source_id"})
            facts.append(
                Fact(_text(fields["key"]), _text(fields["value"]), _text(fields["source_id"]))
            )
        payload = CompleteTask(tuple(facts), _texts(content["gaps"]))
    return ModelDecision(kind, payload)


def validate_brief(
    proposal: CompleteTask,
    context: SuppliedContext,
    tool_evidence: tuple[Fact, ...] = (),
    knowledge_evidence: tuple[Fact, ...] = (),
) -> ResearchBrief:
    """Exact supplied fact matching, not a general natural-language truth oracle."""
    evidence = (*context.facts, *tool_evidence, *knowledge_evidence)
    expected_gaps = {
        key
        for key in context.required_keys
        if len({fact.value for fact in evidence if fact.key == key}) != 1
    }
    keys = [fact.key for fact in proposal.findings]
    if (
        len(set(keys)) != len(keys)
        or set(proposal.gaps) != expected_gaps
        or set(keys) != set(context.required_keys) - expected_gaps
    ):
        raise ModelFailure("unsupported_completion")
    if any(fact not in evidence for fact in proposal.findings):
        raise ModelFailure("ungrounded_fact")
    summary = "; ".join(f"{fact.key}: {fact.value}" for fact in proposal.findings)
    if proposal.gaps:
        summary += "; not supplied or conflicting: " + ", ".join(proposal.gaps)
    return ResearchBrief(
        summary,
        proposal.findings,
        proposal.gaps,
        tuple(sorted({fact.source_id for fact in proposal.findings})),
    )
