"""Authorize, claim, execute outside locks, reconcile, and expose bounded evidence."""

import asyncio
import json
from dataclasses import replace
from hashlib import sha256
from urllib.parse import quote

from agent_company_os.application.tool_validation import input_json, validate_input, validate_output
from agent_company_os.domain.agent import (
    ActionType,
    AgentRun,
    AgentRunId,
    AgentRunStatus,
    Fact,
    Observation,
    ObservationKind,
)
from agent_company_os.domain.decisions import Action, CallTool, ModelFailure
from agent_company_os.domain.errors import InvariantViolation, VersionConflict
from agent_company_os.domain.events import Event, EventType
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.tools import (
    ToolError,
    ToolFailure,
    ToolInvocation,
    ToolInvocationStatus,
    ToolObservationData,
    ToolOutput,
    ToolReceipt,
    ToolRisk,
    ToolVersion,
)
from agent_company_os.domain.transitions import SubjectType
from agent_company_os.ports.clock import Clock
from agent_company_os.ports.ids import IdGenerator
from agent_company_os.ports.runtime_store import RuntimeStore
from agent_company_os.ports.tools import ToolRegistryPort


class ToolRuntimeService:
    def __init__(
        self, store: RuntimeStore, registry: ToolRegistryPort, clock: Clock, ids: IdGenerator
    ) -> None:
        self.store, self.registry, self.clock, self.ids = store, registry, clock, ids

    def descriptors(self, run: AgentRun) -> tuple[ToolVersion, ...]:
        versions = []
        for grant in run.definition_version.allowed_tools:
            try:
                version = self.registry.resolve(run.workspace_id, grant).version
                if version.definition.risk is ToolRisk.READ_ONLY:
                    versions.append(version)
            except ToolFailure:
                continue
        return tuple(versions)

    @staticmethod
    def receipt_facts(receipt: ToolReceipt) -> tuple[Fact, ...]:
        if receipt.output is None:
            return ()
        return tuple(
            Fact(
                f.key,
                f.value,
                f"tool_receipt:{quote(str(receipt.id), safe='')}:{quote(f.source_id, safe='')}",
            )
            for f in receipt.output.facts
        )

    def evidence(self, run: AgentRun) -> tuple[Fact, ...]:
        return tuple(
            fact
            for receipt in self.store.tool_receipts(run.workspace_id, run.id)
            if receipt.invocation.tool_version.grant in run.definition_version.allowed_tools
            and receipt.invocation.status is ToolInvocationStatus.SUCCEEDED
            for fact in self.receipt_facts(receipt)
        )

    def _parents(self, run: AgentRun) -> tuple[Version, ...]:
        domain = self.store.domain
        goal, task = domain.get_goal(run.goal_id), domain.get_task(run.task_id)
        attempt, execution = (
            domain.get_task_attempt(run.task_attempt_id),
            domain.get_execution(run.execution_id),
        )
        if (
            any(item.workspace_id != run.workspace_id for item in (goal, task, attempt, execution))
            or task.goal_id != goal.id
            or attempt.task_id != task.id
            or attempt.execution_id != execution.id
            or execution.goal_id != goal.id
            or (goal.status, task.status, attempt.status, execution.status)
            != ("active", "in_progress", "running", "running")
        ):
            raise ModelFailure("version_conflict")
        return goal.version, task.version, attempt.version, execution.version

    def _event(self, run: AgentRun, kind: EventType, metadata: tuple[tuple[str, str], ...]) -> None:
        self.store.append_event(
            Event(
                self.ids.event_id(),
                run.workspace_id,
                kind,
                SubjectType.AGENT_RUN,
                str(run.id),
                run.version,
                self.clock.now(),
                (
                    ("agent_run_id", str(run.id)),
                    ("execution_id", str(run.execution_id)),
                    ("task_attempt_id", str(run.task_attempt_id)),
                    *metadata,
                ),
            )
        )

    def _observe(self, run: AgentRun, action: Action, data: ToolObservationData) -> AgentRun:
        observation = Observation(
            self.ids.observation_id(),
            run.id,
            run.workspace_id,
            ObservationKind.TOOL_RESULT,
            data.error_code.value if data.error_code else "tool_succeeded",
            action.id,
            provenance="tool_runtime",
            trust="untrusted_tool_data",
            tool_result=data,
        )
        self.store.append_observation(observation)
        state = replace(
            run.working_state,
            invocation_pending=False,
            observations=(*run.working_state.observations, observation)[
                -run.limits.recent_observations :
            ],
        )
        updated = run.evolve(at=self.clock.now(), working_state=state)
        self.store.save_run(updated, run.version, None)
        self._event(
            updated,
            EventType.TOOL_RESULT_OBSERVED,
            (("action_id", str(action.id)), ("observation_id", str(observation.id))),
        )
        return updated

    async def invoke(
        self,
        workspace_id: WorkspaceId,
        run_id: AgentRunId,
        action: Action,
        expected_version: Version,
    ) -> AgentRun:
        with self.store.atomic():
            run = self.store.get_run(workspace_id, run_id)
            payload = action.decision.payload
            if (
                not isinstance(payload, CallTool)
                or action.run_id != run.id
                or self.store.action(workspace_id, action.id) != action
            ):
                raise InvariantViolation("tool_action_binding")
            if ActionType.CALL_TOOL not in run.definition_version.allowed_actions:
                raise ModelFailure("unauthorized_action")
            invocations = self.store.tool_invocations(workspace_id, run_id)
            existing = next((item for item in invocations if item.action_id == action.id), None)
            if existing is not None:
                if existing.status is ToolInvocationStatus.RUNNING:
                    raise InvariantViolation("tool_invocation_in_progress")
                return run  # Same host Action ID replays history, never executes twice.
            if run.version != expected_version:
                raise VersionConflict(
                    "AgentRun", str(run.id), expected_version.value, run.version.value
                )
            if run.status is not AgentRunStatus.RUNNING or not run.working_state.invocation_pending:
                raise InvariantViolation("tool_requires_claimed_running_iteration")
            if action.iteration != run.working_state.iteration:
                raise InvariantViolation("tool_action_iteration")
            parents = self._parents(run)
            if self.clock.now() >= run.deadline:
                raise ModelFailure("deadline_exceeded")
            grant = next(
                (
                    item
                    for item in run.definition_version.allowed_tools
                    if item.tool_id == payload.tool_id
                ),
                None,
            )
            try:
                if grant is None:
                    code = (
                        ToolError.UNAUTHORIZED
                        if self.registry.known(workspace_id, payload.tool_id)
                        else ToolError.NOT_FOUND
                    )
                    raise ToolFailure(code)
                resolved = self.registry.resolve(workspace_id, grant)
                version = resolved.version
                if version.definition.risk is not ToolRisk.READ_ONLY:
                    raise ToolFailure(ToolError.UNAUTHORIZED)
                request = validate_input(payload.arguments_json, version)
            except ToolFailure as error:
                self._event(
                    run,
                    EventType.TOOL_REQUEST_REJECTED,
                    (
                        ("action_id", str(action.id)),
                        ("tool_id", str(payload.tool_id)),
                        ("error_code", error.code.value),
                    ),
                )
                return self._observe(
                    run,
                    action,
                    ToolObservationData(
                        None, payload.tool_id, grant.version if grant else None, error.code
                    ),
                )
            if (
                len(invocations) >= run.limits.max_tool_calls
                or sum(item.tool_version.definition.id == payload.tool_id for item in invocations)
                >= run.limits.max_calls_per_tool
            ):
                raise ModelFailure("tool_budget_exceeded")
            normalized = input_json(request)
            claimed = run.evolve(at=self.clock.now())
            self.store.save_run(claimed, run.version, None)
            invocation = ToolInvocation(
                self.ids.tool_invocation_id(),
                workspace_id,
                run.id,
                action.id,
                run.task_attempt_id,
                run.execution_id,
                version,
                request,
                sha256(
                    json.dumps(
                        [
                            str(workspace_id),
                            str(run.id),
                            str(action.id),
                            str(version.definition.id),
                            version.version.value,
                            normalized,
                        ],
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
                claimed.version,
                parents,
                resolved.revision,
                self.clock.now(),
            )
            self.store.add_tool_invocation(invocation)
            self._event(
                claimed,
                EventType.TOOL_INVOCATION_STARTED,
                (
                    ("tool_invocation_id", str(invocation.id)),
                    ("tool_id", str(payload.tool_id)),
                    ("tool_version", str(version.version.value)),
                    ("action_id", str(action.id)),
                ),
            )
        output: ToolOutput | None = None
        error_code: ToolError | None = None
        output_bytes = 0
        cancelled = False
        try:
            raw = await asyncio.wait_for(
                resolved.executor.execute(request, invocation),
                min(version.timeout_seconds, (run.deadline - self.clock.now()).total_seconds()),
            )
            # Size recorded only for bounded output. Never retain oversized raw payloads.
            output = validate_output(raw, version, request)
            output_bytes = len(raw.encode("utf-8"))
        except TimeoutError:
            error_code = ToolError.TIMEOUT
        except asyncio.CancelledError:
            error_code, cancelled = ToolError.CANCELLED, True
        except ToolFailure as error:
            error_code = error.code
        except Exception:
            error_code = ToolError.INTERNAL_EXECUTOR_ERROR
        try:
            result = self._reconcile(
                invocation, action, output, error_code, len(normalized.encode()), output_bytes
            )
        except Exception:
            # A failed commit must not trigger another executor call. Best-effort failure receipt.
            self._reconcile(
                invocation,
                action,
                None,
                ToolError.INTERNAL_EXECUTOR_ERROR,
                len(normalized.encode()),
                0,
            )
            raise
        if cancelled:
            raise asyncio.CancelledError
        if result.status is AgentRunStatus.RUNNING and result.working_state.invocation_pending:
            raise ModelFailure("version_conflict")
        return result

    def _reconcile(
        self,
        invocation: ToolInvocation,
        action: Action,
        output: ToolOutput | None,
        error: ToolError | None,
        input_bytes: int,
        output_bytes: int,
    ) -> AgentRun:
        with self.store.atomic():
            run = self.store.get_run(invocation.workspace_id, invocation.run_id)
            terminal = run.status not in (AgentRunStatus.RUNNING, AgentRunStatus.WAITING)
            stale = run.version != invocation.run_version
            if terminal:
                error = (
                    ToolError.CANCELLED
                    if run.status is AgentRunStatus.CANCELLED
                    else ToolError.STALE_RESULT
                )
            else:
                try:
                    stale = stale or self._parents(run) != invocation.parent_versions
                    current = self.registry.resolve(run.workspace_id, invocation.tool_version.grant)
                    stale = stale or current.revision != invocation.registry_revision
                except (ModelFailure, ToolFailure):
                    stale = True
                if stale:
                    error = ToolError.STALE_RESULT
                elif self.clock.now() >= run.deadline:
                    error = ToolError.TIMEOUT
            if error is not None:
                output = None
                output_bytes = 0
            finished = invocation.finish(self.clock.now(), error)
            receipt = ToolReceipt(
                self.ids.tool_receipt_id(),
                finished,
                output,
                input_bytes,
                output_bytes,
                "observed" if error is None else "unknown",
            )
            self.store.finish_tool_invocation(receipt)
            duration = max(
                0, int((self.clock.now() - invocation.started_at).total_seconds() * 1000)
            )
            self._event(
                run,
                EventType.TOOL_RECEIPT_RECORDED,
                (
                    ("tool_invocation_id", str(invocation.id)),
                    ("tool_receipt_id", str(receipt.id)),
                    ("tool_id", str(invocation.tool_version.definition.id)),
                    ("tool_version", str(invocation.tool_version.version.value)),
                    ("status", finished.status.value),
                    ("error_code", error.value if error else "none"),
                    ("duration_ms", str(duration)),
                    ("input_bytes", str(input_bytes)),
                    ("output_bytes", str(output_bytes)),
                    ("retry_count", "0"),
                ),
            )
            if terminal or stale:
                return run  # History only: never apply late results to newer state.
            data = ToolObservationData(
                receipt.id,
                invocation.tool_version.definition.id,
                invocation.tool_version.version,
                error,
                self.receipt_facts(receipt)[:5],
                output.notes if output else "",
            )
            return self._observe(run, action, data)
