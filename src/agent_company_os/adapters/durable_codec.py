"""Schema-v1 JSON codec for the deterministic domain persistence boundary.

Only explicitly registered data classes can be reconstructed. No imports, pickle,
default filling, or executable objects are accepted from persisted input.
"""

import json
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from types import UnionType
from typing import Any, get_args, get_origin, get_type_hints

from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.events import Event
from agent_company_os.domain.execution import Execution, ExecutionBounds
from agent_company_os.domain.goal import Goal
from agent_company_os.domain.ids import (
    EventId,
    ExecutionId,
    GoalId,
    StateTransitionId,
    TaskAttemptId,
    TaskId,
    Version,
    WorkspaceId,
)
from agent_company_os.domain.task import Task
from agent_company_os.domain.task_attempt import TaskAttempt
from agent_company_os.domain.transitions import StateTransition
from agent_company_os.domain.validation import require_utc
from agent_company_os.domain.workspace import Workspace

_RECORD_TYPES: tuple[type[object], ...] = (
    Workspace,
    Goal,
    Task,
    TaskAttempt,
    Execution,
    ExecutionBounds,
    Event,
    StateTransition,
    WorkspaceId,
    GoalId,
    TaskId,
    TaskAttemptId,
    ExecutionId,
    EventId,
    StateTransitionId,
    Version,
)


def _invalid() -> InvariantViolation:
    return InvariantViolation("invalid_durable_record")


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise _invalid()
        result[key] = value
    return result


def _encode(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        require_utc(value, "persisted_timestamp")
        return value.isoformat()
    if type(value) in _RECORD_TYPES and is_dataclass(value):
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise _invalid()


def _decode(value: object, expected: Any) -> Any:
    """Type hints describe a fixed allowlisted schema, not caller-selected types."""
    origin = get_origin(expected)
    if origin is UnionType:
        for option in get_args(expected):
            try:
                return _decode(value, option)
            except (InvariantViolation, TypeError, ValueError):
                continue
        raise _invalid()
    if origin is tuple:
        if not isinstance(value, list):
            raise _invalid()
        args = get_args(expected)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(item, args[0]) for item in value)
        if len(value) != len(args):
            raise _invalid()
        return tuple(_decode(item, kind) for item, kind in zip(value, args, strict=True))
    if expected is type(None):
        if value is not None:
            raise _invalid()
        return None
    if expected in (str, int, bool):
        if type(value) is not expected:
            raise _invalid()
        return value
    if expected is datetime:
        if not isinstance(value, str):
            raise _invalid()
        stamp = datetime.fromisoformat(value)
        require_utc(stamp, "persisted_timestamp")
        return stamp
    if isinstance(expected, type) and issubclass(expected, Enum):
        if type(value) not in (str, int):
            raise _invalid()
        return expected(value)
    if expected in _RECORD_TYPES:
        if not isinstance(value, dict):
            raise _invalid()
        names = {field.name for field in fields(expected)}
        if set(value) != names:
            raise _invalid()
        hints = get_type_hints(expected)
        return expected(**{name: _decode(value[name], hints[name]) for name in names})
    raise _invalid()


def encode_record(record: object) -> str:
    if type(record) not in _RECORD_TYPES:
        raise _invalid()
    payload = _encode(record)
    # Validate even records constructed by bypassing annotations or frozen setters.
    _decode(payload, type(record))
    return json.dumps(
        {"schema_version": 1, "type": type(record).__name__, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def decode_record[T](serialized: str, expected: type[T]) -> T:
    try:
        envelope = json.loads(serialized, object_pairs_hook=_pairs)
        if (
            not isinstance(envelope, dict)
            or set(envelope) != {"schema_version", "type", "payload"}
            or type(envelope["schema_version"]) is not int
            or envelope["schema_version"] != 1
            or envelope["type"] != expected.__name__
            or expected not in _RECORD_TYPES
        ):
            raise _invalid()
        record: T = _decode(envelope["payload"], expected)
        return record
    except (TypeError, ValueError, KeyError, AttributeError, RecursionError) as error:
        raise _invalid() from error
