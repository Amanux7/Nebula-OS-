"""Versioned, read-only tool contracts and immutable execution evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.ids import ExecutionId, OpaqueId, TaskAttemptId, Version, WorkspaceId
from agent_company_os.domain.validation import require_utc

if TYPE_CHECKING:
    from agent_company_os.domain.agent import ActionId, AgentRunId, Fact


class ToolId(OpaqueId):
    pass


class ToolInvocationId(OpaqueId):
    pass


class ToolReceiptId(OpaqueId):
    pass


class ToolRisk(StrEnum):
    READ_ONLY = "read_only"
    INTERNAL_WRITE = "internal_write"
    EXTERNAL_WRITE = "external_write"
    HIGH_RISK = "high_risk"


class ExecutorKind(StrEnum):
    SEND_FIXTURE_MESSAGE = "send_fixture_message"
    COMPANY_LOOKUP = "company_lookup"
    SOURCE_LOOKUP = "source_lookup"


class ToolError(StrEnum):
    REJECTED = "rejected"
    VALIDATION_ERROR = "validation_error"
    UNAUTHORIZED = "unauthorized"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    MALFORMED_OUTPUT = "malformed_output"
    CANCELLED = "cancelled"
    INTERNAL_EXECUTOR_ERROR = "internal_executor_error"
    OUTPUT_TOO_LARGE = "output_too_large"
    STALE_RESULT = "stale_result"


class ToolFailure(Exception):
    def __init__(self, code: ToolError) -> None:
        self.code = code if isinstance(code, ToolError) else ToolError.INTERNAL_EXECUTOR_ERROR
        super().__init__(self.code.value)


@dataclass(frozen=True)
class ToolGrant:
    tool_id: ToolId
    version: Version


@dataclass(frozen=True)
class ToolDefinition:
    id: ToolId
    workspace_id: WorkspaceId
    name: str
    description: str
    risk: ToolRisk = ToolRisk.READ_ONLY


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 0

    def __post_init__(self) -> None:
        if type(self.max_retries) is not int or self.max_retries != 0:
            raise InvariantViolation("stage3_no_automatic_retries")

    def should_retry(self, error: ToolError) -> bool:
        return False


@dataclass(frozen=True)
class ToolVersion:
    definition: ToolDefinition
    version: Version
    executor_kind: ExecutorKind
    input_schema: str
    output_schema: str = "facts.v1"
    timeout_seconds: int = 3
    max_input_bytes: int = 2048
    max_output_bytes: int = 8192
    retry_policy: RetryPolicy = RetryPolicy()
    trust: str = "trusted_runtime_fixture"

    def __post_init__(self) -> None:
        if (
            self.input_schema != f"{self.executor_kind.value}.v1"
            or self.output_schema != "facts.v1"
        ):
            raise InvariantViolation("unsupported_tool_contract")
        for value, maximum in (
            (self.timeout_seconds, 30),
            (self.max_input_bytes, 4096),
            (self.max_output_bytes, 16384),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise InvariantViolation("tool_limit_range")
        if self.trust != "trusted_runtime_fixture":
            raise InvariantViolation("stage3_fixture_trust_only")
        for text in (self.definition.name, self.definition.description):
            if not text.strip() or len(text) > 500:
                raise InvariantViolation("tool_description_size")

    @property
    def grant(self) -> ToolGrant:
        return ToolGrant(self.definition.id, self.version)


@dataclass(frozen=True)
class CompanyLookupInput:
    company_name: str


@dataclass(frozen=True)
class SourceLookupInput:
    source_id: str
    keys: tuple[str, ...]


@dataclass(frozen=True)
class FixtureMessageInput:
    destination: str
    message: str


type ToolInput = CompanyLookupInput | SourceLookupInput | FixtureMessageInput


@dataclass(frozen=True)
class ToolOutput:
    subject: str
    facts: tuple[Fact, ...]
    notes: str = ""


class ToolInvocationStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ToolInvocation:
    id: ToolInvocationId
    workspace_id: WorkspaceId
    run_id: AgentRunId
    action_id: ActionId
    task_attempt_id: TaskAttemptId
    execution_id: ExecutionId
    tool_version: ToolVersion
    validated_input: ToolInput
    request_fingerprint: str
    run_version: Version
    parent_versions: tuple[Version, ...]
    registry_revision: int
    started_at: datetime
    version: Version = Version(1)
    status: ToolInvocationStatus = ToolInvocationStatus.RUNNING
    ended_at: datetime | None = None
    error_code: ToolError | None = None

    def __post_init__(self) -> None:
        require_utc(self.started_at, "tool_start")
        terminal = self.status is not ToolInvocationStatus.RUNNING
        if terminal != (self.ended_at is not None):
            raise InvariantViolation("tool_terminal_end_time")
        if self.tool_version.definition.workspace_id != self.workspace_id:
            raise InvariantViolation("tool_invocation_scope")
        if self.ended_at is not None:
            require_utc(self.ended_at, "tool_end")
            if self.ended_at < self.started_at:
                raise InvariantViolation("tool_time_order")
        if (self.status in (ToolInvocationStatus.FAILED, ToolInvocationStatus.CANCELLED)) != (
            self.error_code is not None
        ):
            raise InvariantViolation("tool_failure_reason")
        if len(self.request_fingerprint) != 64 or any(
            c not in "0123456789abcdef" for c in self.request_fingerprint
        ):
            raise InvariantViolation("tool_request_digest")

    def finish(self, at: datetime, error: ToolError | None = None) -> ToolInvocation:
        if self.status is not ToolInvocationStatus.RUNNING:
            raise InvariantViolation("terminal_tool_invocation_immutable")
        require_utc(at, "tool_end")
        if at < self.started_at:
            raise InvariantViolation("tool_time_order")
        status = ToolInvocationStatus.SUCCEEDED if error is None else ToolInvocationStatus.FAILED
        if error is ToolError.CANCELLED:
            status = ToolInvocationStatus.CANCELLED
        return replace(
            self, status=status, ended_at=at, error_code=error, version=self.version.next()
        )


@dataclass(frozen=True)
class ToolReceipt:
    id: ToolReceiptId
    invocation: ToolInvocation
    output: ToolOutput | None
    input_bytes: int
    output_bytes: int
    remote_outcome: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.invocation.status is ToolInvocationStatus.RUNNING or self.schema_version != 1:
            raise InvariantViolation("receipt_requires_terminal_invocation")
        if (self.invocation.status is ToolInvocationStatus.SUCCEEDED) != (self.output is not None):
            raise InvariantViolation("receipt_success_requires_validated_output")
        if (
            type(self.input_bytes) is not int
            or type(self.output_bytes) is not int
            or not 0 < self.input_bytes <= self.invocation.tool_version.max_input_bytes
            or not 0 <= self.output_bytes <= self.invocation.tool_version.max_output_bytes
            or self.remote_outcome
            != (
                "observed"
                if self.output is not None
                else "observed_failure"
                if self.invocation.error_code is ToolError.REJECTED
                else "unknown"
            )
        ):
            raise InvariantViolation("receipt_metadata_contract")


@dataclass(frozen=True)
class ToolObservationData:
    receipt_id: ToolReceiptId | None
    tool_id: ToolId
    tool_version: Version | None
    error_code: ToolError | None
    facts: tuple[Fact, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.facts, tuple) or len(self.facts) > 5 or len(self.notes) > 512:
            raise InvariantViolation("tool_observation_bounds")
        if self.error_code is None and self.receipt_id is None:
            raise InvariantViolation("tool_success_requires_receipt")
        if self.error_code is not None and self.facts:
            raise InvariantViolation("failed_tool_has_no_evidence")
