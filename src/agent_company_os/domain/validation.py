"""Shared deterministic validation helpers."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from agent_company_os.domain.errors import InvariantViolation


def clean_required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise InvariantViolation("required_text", details={"field": field_name})
    return cleaned


def clean_optional_texts(values: Iterable[str], field_name: str) -> tuple[str, ...]:
    cleaned = tuple(value.strip() for value in values)
    if any(not value for value in cleaned):
        raise InvariantViolation("non_empty_text_items", details={"field": field_name})
    return cleaned


def clean_required_texts(values: Iterable[str], field_name: str) -> tuple[str, ...]:
    cleaned = clean_optional_texts(values, field_name)
    if not cleaned:
        raise InvariantViolation("required_text_items", details={"field": field_name})
    return cleaned


def require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise InvariantViolation("utc_aware_datetime", details={"field": field_name})


def require_monotonic_time(previous: datetime, current: datetime, field_name: str) -> None:
    require_utc(current, field_name)
    if current < previous:
        raise InvariantViolation(
            "monotonic_time",
            details={"field": field_name, "previous": previous.isoformat()},
        )
