"""Recovery describes evidence, never guesses about remote execution."""

import json
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from agent_company_os.domain.ids import WorkspaceId
from agent_company_os.domain.tools import ToolInvocation


class RemoteStatus(StrEnum):
    NEVER_RECEIVED = "never_received"
    PROCESSED_SUCCESS = "processed_success"
    PROCESSED_FAILURE = "processed_failure"
    UNKNOWN = "unknown"


class RecoveryReason(StrEnum):
    RESUME_LOCAL = "resume_local_state"
    SAFE_TO_RETRY = "safe_to_retry"
    AWAITING_APPROVAL = "awaiting_human_approval"
    CONNECTOR_REQUIRED = "connector_reconciliation_required"
    MANUAL_REVIEW = "manual_review_required"
    TERMINAL_UNKNOWN = "terminal_unknown"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ConnectorCapabilities:
    supports_idempotency_key: bool = False
    supports_status_lookup: bool = False
    supports_remote_cancel: bool = False
    supports_compensation: bool = False


@dataclass(frozen=True)
class RemoteLookup:
    status: RemoteStatus
    output_json: str | None = None


@dataclass(frozen=True)
class RecoveryCase:
    workspace_id: WorkspaceId
    subject_type: str
    subject_id: str
    reason: RecoveryReason
    outcome: str


class RetentionClass(StrEnum):
    OPERATIONAL = "operational"
    AUDIT = "audit"
    SENSITIVE = "sensitive"
    EPHEMERAL = "ephemeral"


@dataclass(frozen=True)
class ContentTombstone:
    """Future redaction representation, not an enabled deletion command."""

    workspace_id: WorkspaceId
    record_type: str
    record_id: str
    digest: str
    reason_code: str
    content_available: bool = False


def execution_key(invocation: ToolInvocation) -> str:
    return sha256(
        json.dumps(
            [
                str(invocation.workspace_id),
                "intent:" + str(invocation.action_id),
                str(invocation.id),
                str(invocation.tool_version.definition.id),
                invocation.tool_version.version.value,
            ],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
