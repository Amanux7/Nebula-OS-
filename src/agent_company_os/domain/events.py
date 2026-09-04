"""Minimal immutable audit Events; canonical entity state is stored separately."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.ids import EventId, Version, WorkspaceId
from agent_company_os.domain.transitions import SubjectType
from agent_company_os.domain.validation import clean_required_text, require_utc


class EventType(StrEnum):
    ORCHESTRATION_STARTED = "orchestration_started"
    PLAN_PROPOSED = "plan_proposed"
    PLAN_REJECTED = "plan_rejected"
    PLAN_ACCEPTED = "plan_accepted"
    PLAN_MATERIALIZED = "plan_materialized"
    TASK_DELEGATED = "task_delegated"
    DELEGATION_REJECTED = "delegation_rejected"
    REPLAN_REQUESTED = "replan_requested"
    REPLAN_COMPLETED = "replan_completed"
    ORCHESTRATION_COMPLETED = "orchestration_completed"
    ORCHESTRATION_FAILED = "orchestration_failed"
    ORCHESTRATION_CANCELLED = "orchestration_cancelled"
    MEMORY_CANDIDATE_CREATED = "memory_candidate_created"
    MEMORY_REVIEW_REQUESTED = "memory_review_requested"
    MEMORY_CANDIDATE_REJECTED = "memory_candidate_rejected"
    MEMORY_PROMOTED = "memory_promoted"
    MEMORY_REVOKED = "memory_revoked"
    MEMORY_SUPERSEDED = "memory_superseded"
    MEMORY_RETRIEVED = "memory_retrieved"
    MEMORY_CONTEXT_PACK_CREATED = "memory_context_pack_created"
    KNOWLEDGE_SOURCE_PUBLISHED = "knowledge_source_published"
    KNOWLEDGE_SOURCE_DISABLED = "knowledge_source_disabled"
    KNOWLEDGE_QUERY_EXECUTED = "knowledge_query_executed"
    KNOWLEDGE_QUERY_REJECTED = "knowledge_query_rejected"
    EVIDENCE_PACK_CREATED = "evidence_pack_created"
    TOOL_INVOCATION_STARTED = "tool_invocation_started"
    TOOL_REQUEST_REJECTED = "tool_request_rejected"
    TOOL_RECEIPT_RECORDED = "tool_receipt_recorded"
    TOOL_RESULT_OBSERVED = "tool_result_observed"
    AGENT_RUN_STARTED = "agent_run_started"
    MODEL_INVOCATION_REQUESTED = "model_invocation_requested"
    MODEL_INVOCATION_FAILED = "model_invocation_failed"
    MODEL_DECISION_RECEIVED = "model_decision_received"
    MODEL_DECISION_REJECTED = "model_decision_rejected"
    ACTION_REQUESTED = "action_requested"
    ACTION_ACCEPTED = "action_accepted"
    OBSERVATION_RECORDED = "observation_recorded"
    AGENT_WAITING_FOR_CONTEXT = "agent_waiting_for_context"
    AGENT_RUN_RESUMED = "agent_run_resumed"
    AGENT_RUN_COMPLETED = "agent_run_completed"
    AGENT_RUN_FAILED = "agent_run_failed"
    AGENT_RUN_CANCELLED = "agent_run_cancelled"
    WORKSPACE_CREATED = "workspace_created"
    GOAL_CREATED = "goal_created"
    GOAL_ACTIVATED = "goal_activated"
    GOAL_SATISFIED = "goal_satisfied"
    GOAL_CLOSED_UNSATISFIED = "goal_closed_unsatisfied"
    GOAL_CANCELLED = "goal_cancelled"
    TASK_CREATED = "task_created"
    TASK_READY = "task_ready"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_RETRY_READY = "task_retry_ready"
    TASK_BLOCKED = "task_blocked"
    TASK_UNBLOCKED = "task_unblocked"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"
    TASK_ATTEMPT_CREATED = "task_attempt_created"
    TASK_ATTEMPT_STARTED = "task_attempt_started"
    TASK_ATTEMPT_SUCCEEDED = "task_attempt_succeeded"
    TASK_ATTEMPT_FAILED = "task_attempt_failed"
    TASK_ATTEMPT_CANCELLED = "task_attempt_cancelled"
    EXECUTION_CREATED = "execution_created"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_WAITING = "execution_waiting"
    EXECUTION_RESUMED = "execution_resumed"
    EXECUTION_SUCCEEDED = "execution_succeeded"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_CANCELLED = "execution_cancelled"


@dataclass(frozen=True, slots=True)
class Event:
    id: EventId
    workspace_id: WorkspaceId
    event_type: EventType
    subject_type: SubjectType
    subject_id: str
    entity_version: Version
    occurred_at: datetime
    metadata: tuple[tuple[str, str], ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        clean_required_text(self.subject_id, "subject_id")
        require_utc(self.occurred_at, "occurred_at")
        if self.schema_version != 1:
            raise InvariantViolation(
                "event_schema_version_supported",
                details={"schema_version": str(self.schema_version)},
            )
        keys = [key for key, _ in self.metadata]
        if len(keys) != len(set(keys)):
            raise InvariantViolation("event_metadata_keys_unique")
        for key, value in self.metadata:
            clean_required_text(key, "metadata_key")
            clean_required_text(value, "metadata_value")
