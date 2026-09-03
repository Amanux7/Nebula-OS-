"""Single-agent runtime: models propose; deterministic software commits."""

import asyncio
from dataclasses import dataclass, replace
from datetime import timedelta

from agent_company_os.application.context import ActionPolicy, ContextAssembler
from agent_company_os.application.service import DomainService
from agent_company_os.domain.agent import (
    ActionType,
    AgentDefinitionId,
    AgentRun,
    AgentRunId,
    AgentRunStatus,
    Observation,
    ObservationKind,
    RuntimeLimits,
    SuppliedContext,
)
from agent_company_os.domain.decisions import (
    Action,
    CallTool,
    CompleteTask,
    ModelFailure,
    RequestMoreContext,
    parse_decision,
    validate_brief,
)
from agent_company_os.domain.errors import (
    DomainError,
    InvariantViolation,
    VersionConflict,
    WorkspaceMismatch,
)
from agent_company_os.domain.events import Event, EventType
from agent_company_os.domain.execution import Execution, ExecutionStatus
from agent_company_os.domain.goal import Goal, GoalStatus
from agent_company_os.domain.ids import TaskAttemptId, Version, WorkspaceId
from agent_company_os.domain.task import Task, TaskStatus
from agent_company_os.domain.task_attempt import TaskAttempt, TaskAttemptStatus
from agent_company_os.domain.transitions import StateTransition, SubjectType
from agent_company_os.ports.clock import Clock
from agent_company_os.ports.ids import IdGenerator
from agent_company_os.ports.knowledge import KnowledgeRuntimePort
from agent_company_os.ports.model import ModelPort
from agent_company_os.ports.runtime_store import RuntimeStore
from agent_company_os.ports.tools import ToolRuntimePort


@dataclass(frozen=True)
class RuntimeSnapshot:
    goal: Goal
    task: Task
    attempt: TaskAttempt
    execution: Execution

    @property
    def versions(self) -> tuple[Version, ...]:
        return (self.goal.version, self.task.version, self.attempt.version, self.execution.version)


class AgentRuntimeService:
    def __init__(
        self,
        store: RuntimeStore,
        clock: Clock,
        ids: IdGenerator,
        model: ModelPort,
        tools: ToolRuntimePort | None = None,
        knowledge: KnowledgeRuntimePort | None = None,
    ) -> None:
        self.store = store
        self.clock = clock
        self.ids = ids
        self.model = model
        self.tools = tools
        self.knowledge = knowledge
        self.domain = DomainService(store.domain, clock, ids)
        self.assembler = ContextAssembler()
        self.policy = ActionPolicy()

    def start(
        self,
        workspace_id: WorkspaceId,
        definition_id: AgentDefinitionId,
        definition_version: Version,
        attempt_id: TaskAttemptId,
        context: SuppliedContext,
        limits: RuntimeLimits | None = None,
    ) -> AgentRun:
        with self.store.atomic():
            limits = limits or RuntimeLimits()
            definition = self.store.definition(workspace_id, definition_id, definition_version)
            attempt = self.store.domain.get_task_attempt(attempt_id)
            task = self.store.domain.get_task(attempt.task_id)
            if definition.model_name != self.model.model_name:
                raise InvariantViolation("model_must_match_published_configuration")
            run = AgentRun(
                self.ids.agent_run_id(),
                workspace_id,
                attempt.execution_id,
                attempt.id,
                task.id,
                task.goal_id,
                definition,
                limits,
                context,
                self.clock.now(),
                self.clock.now() + timedelta(seconds=limits.execution_seconds),
                runtime_protocol="single-agent-knowledge-v1"
                if definition.knowledge_scope.source_ids
                else "single-agent-tools-v1"
                if ActionType.CALL_TOOL in definition.allowed_actions
                else "single-agent-v1",
                policy_version="bounded-knowledge-tools-v1"
                if definition.knowledge_scope.source_ids
                else "read-only-tools-v1"
                if ActionType.CALL_TOOL in definition.allowed_actions
                else "internal-actions-v1",
                evaluator_version="knowledge-facts-v1"
                if definition.knowledge_scope.source_ids
                else "receipt-facts-v1"
                if ActionType.CALL_TOOL in definition.allowed_actions
                else "supplied-facts-v1",
            )
            self._parents(run)
            self.store.add_run(run)
            self._event(run, EventType.AGENT_RUN_STARTED)
            return run

    def _parents(self, run: AgentRun, *, waiting: bool = False) -> RuntimeSnapshot:
        attempt = self.store.domain.get_task_attempt(run.task_attempt_id)
        task = self.store.domain.get_task(run.task_id)
        execution = self.store.domain.get_execution(run.execution_id)
        goal = self.store.domain.get_goal(run.goal_id)
        for workspace_id in (
            attempt.workspace_id,
            task.workspace_id,
            execution.workspace_id,
            goal.workspace_id,
            run.context.workspace_id,
            run.definition_version.definition.workspace_id,
        ):
            if workspace_id != run.workspace_id:
                raise WorkspaceMismatch("AgentRun", str(run.workspace_id), str(workspace_id))
        if (
            attempt.task_id != task.id
            or attempt.execution_id != execution.id
            or task.goal_id != goal.id
            or execution.goal_id != goal.id
            or run.context.task_id != task.id
        ):
            raise InvariantViolation("runtime_parent_bindings")
        expected_execution = ExecutionStatus.WAITING if waiting else ExecutionStatus.RUNNING
        if (
            attempt.status is not TaskAttemptStatus.RUNNING
            or task.status is not TaskStatus.IN_PROGRESS
            or execution.status is not expected_execution
            or goal.status is not GoalStatus.ACTIVE
        ):
            raise InvariantViolation("runtime_parents_must_be_active")
        return RuntimeSnapshot(goal, task, attempt, execution)

    @staticmethod
    def _version(run: AgentRun, expected: Version) -> None:
        if run.version != expected:
            raise VersionConflict("AgentRun", str(run.id), expected.value, run.version.value)

    async def drive(
        self,
        workspace_id: WorkspaceId,
        run_id: AgentRunId,
        expected_version: Version,
    ) -> AgentRun:
        # Reject duplicate callers before failure recovery; they do not own this invocation.
        with self.store.atomic():
            run = self.store.get_run(workspace_id, run_id)
            self._version(run, expected_version)
            if run.status is not AgentRunStatus.RUNNING or run.working_state.invocation_pending:
                raise InvariantViolation("run_not_available_for_drive")
        for _ in range(run.limits.max_iterations - run.working_state.iteration):
            try:
                with self.store.atomic():
                    run = self.store.get_run(workspace_id, run_id)
                    snapshot = self._parents(run)
                    self._deadline(run)
                    if self.model.model_name != run.definition_version.model_name:
                        raise InvariantViolation("model_binding_changed")
                    tool_enabled = ActionType.CALL_TOOL in run.definition_version.allowed_actions
                    knowledge_enabled = bool(run.definition_version.knowledge_scope.source_ids)
                    if (
                        run.policy_version != self.policy.version_for(run)
                        or run.runtime_protocol
                        != (
                            "single-agent-knowledge-v1"
                            if knowledge_enabled
                            else "single-agent-tools-v1"
                            if tool_enabled
                            else "single-agent-v1"
                        )
                        or run.evaluator_version
                        != (
                            "knowledge-facts-v1"
                            if knowledge_enabled
                            else "receipt-facts-v1"
                            if tool_enabled
                            else "supplied-facts-v1"
                        )
                    ):
                        raise InvariantViolation("runtime_configuration_version_changed")
                    if run.working_state.invocation_pending:
                        raise InvariantViolation("duplicate_invocation")
                    if (
                        run.working_state.active_evidence_pack_id is not None
                        and self.knowledge is None
                    ):
                        raise InvariantViolation("knowledge_adapter_required")
                    state = replace(
                        run.working_state,
                        iteration=run.working_state.iteration + 1,
                        invocation_pending=True,
                    )
                    claimed = run.evolve(at=self.clock.now(), working_state=state)
                    self._save(run, claimed, EventType.MODEL_INVOCATION_REQUESTED)
                    request = self.assembler.assemble(
                        claimed,
                        snapshot.goal,
                        snapshot.task,
                        self.tools.descriptors(claimed) if self.tools else (),
                        self.knowledge.active_pack(claimed) if self.knowledge else None,
                    )
                    started = self.clock.now()
                # Never hold a store lock across a model call. Adapter is cooperative async.
                remaining = (claimed.deadline - self.clock.now()).total_seconds()
                try:
                    raw = await asyncio.wait_for(
                        self.model.invoke(request),
                        timeout=min(claimed.limits.model_seconds, remaining),
                    )
                except (TimeoutError, ModelFailure):
                    raise
                except Exception as error:
                    raise ModelFailure("provider_unavailable") from error
                decision = parse_decision(raw, claimed.limits.max_response_chars)
                if isinstance(decision.payload, CallTool):
                    with self.store.atomic():
                        current = self.store.get_run(workspace_id, run_id)
                        self._version(current, claimed.version)
                        self._deadline(current)
                        if self.knowledge:
                            self.knowledge.active_pack(current)
                        if self._parents(current).versions != snapshot.versions:
                            raise ModelFailure("version_conflict")
                        self.policy.authorize(current, decision)
                        if self.tools is None:
                            raise ModelFailure("unauthorized_action")
                        action = Action(
                            self.ids.action_id(),
                            current.id,
                            workspace_id,
                            decision,
                            current.working_state.iteration,
                        )
                        self.store.append_action(action)
                        self._event(current, EventType.MODEL_DECISION_RECEIVED)
                        self._event(
                            current,
                            EventType.ACTION_REQUESTED,
                            (("action_type", decision.action_type.value),),
                        )
                    run = await self.tools.invoke(workspace_id, run_id, action, current.version)
                    if run.status is not AgentRunStatus.RUNNING:
                        return run
                    continue
                with self.store.atomic():
                    current = self.store.get_run(workspace_id, run_id)
                    self._version(current, claimed.version)
                    self._deadline(current)
                    if self.knowledge:
                        self.knowledge.active_pack(current)
                    versions = (
                        self.store.domain.get_goal(current.goal_id).version,
                        self.store.domain.get_task(current.task_id).version,
                        self.store.domain.get_task_attempt(current.task_attempt_id).version,
                        self.store.domain.get_execution(current.execution_id).version,
                    )
                    if versions != snapshot.versions:
                        raise ModelFailure("version_conflict")
                    latest = self._parents(current)
                    duration = max(0, int((self.clock.now() - started).total_seconds() * 1000))
                    self._event(
                        current,
                        EventType.MODEL_DECISION_RECEIVED,
                        (("duration_ms", str(duration)),),
                    )
                    decision = parse_decision(raw, current.limits.max_response_chars)
                    action = Action(
                        self.ids.action_id(),
                        current.id,
                        workspace_id,
                        decision,
                        current.working_state.iteration,
                    )
                    self.store.append_action(action)
                    self._event(
                        current,
                        EventType.ACTION_REQUESTED,
                        (("action_type", decision.action_type.value),),
                    )
                    self.policy.authorize(current, decision)
                    status = AgentRunStatus.RUNNING
                    result = None
                    missing: tuple[str, ...] = ()
                    kind = ObservationKind.ACTION_ACCEPTED
                    if isinstance(decision.payload, CompleteTask):
                        result = validate_brief(
                            decision.payload,
                            current.context,
                            self.tools.evidence(current) if self.tools else (),
                            self.knowledge.evidence(current) if self.knowledge else (),
                        )
                        attempt = self.domain.succeed_task_attempt(
                            latest.attempt.id, latest.attempt.version
                        )
                        self.domain.complete_task(latest.task.id, attempt.id, latest.task.version)
                        tasks = self.store.domain.tasks_for_goal(latest.goal.id)
                        if all(task.status is TaskStatus.COMPLETED for task in tasks):
                            self.domain.succeed_execution(
                                latest.execution.id, latest.execution.version
                            )
                        status = AgentRunStatus.SUCCEEDED
                        kind = ObservationKind.COMPLETION_RESULT
                    elif isinstance(decision.payload, RequestMoreContext):
                        missing = decision.payload.missing_fields
                        if not set(missing) <= set(current.context.required_keys):
                            raise ModelFailure("unsupported_context_request")
                        self.domain.wait_execution(latest.execution.id, latest.execution.version)
                        status = AgentRunStatus.WAITING
                    observation = Observation(
                        self.ids.observation_id(),
                        current.id,
                        workspace_id,
                        kind,
                        decision.action_type.value,
                        action.id,
                    )
                    self.store.append_observation(observation)
                    state = replace(
                        current.working_state,
                        invocation_pending=False,
                        missing_fields=missing,
                        observations=(*current.working_state.observations, observation)[
                            -current.limits.recent_observations :
                        ],
                    )
                    updated = current.evolve(
                        at=self.clock.now(), status=status, working_state=state, result=result
                    )
                    event_type = {
                        AgentRunStatus.RUNNING: EventType.ACTION_ACCEPTED,
                        AgentRunStatus.WAITING: EventType.AGENT_WAITING_FOR_CONTEXT,
                        AgentRunStatus.SUCCEEDED: EventType.AGENT_RUN_COMPLETED,
                    }[status]
                    self._save(current, updated, event_type)
                    if event_type is not EventType.ACTION_ACCEPTED:
                        self._event(
                            updated,
                            EventType.ACTION_ACCEPTED,
                            (("action_type", decision.action_type.value),),
                        )
                    self._event(
                        updated,
                        EventType.OBSERVATION_RECORDED,
                        (("observation_id", str(observation.id)),),
                    )
                    run = updated
                if run.status is not AgentRunStatus.RUNNING:
                    return run
            except TimeoutError:
                code = "deadline_exceeded" if self.clock.now() >= run.deadline else "model_timeout"
                return self._failure(workspace_id, run_id, code)
            except asyncio.CancelledError:
                self._failure(workspace_id, run_id, "cancelled", cancelled=True)
                raise
            except ModelFailure as error:
                return self._failure(workspace_id, run_id, error.code)
            except DomainError as error:
                return self._failure(workspace_id, run_id, error.code)
            except Exception:
                # Do not leak provider exception text, credentials or arbitrary model payloads.
                return self._failure(workspace_id, run_id, "runtime_error")
        return self._failure(workspace_id, run_id, "iteration_limit_exceeded")

    def resume(
        self,
        workspace_id: WorkspaceId,
        run_id: AgentRunId,
        expected_version: Version,
        context: SuppliedContext,
    ) -> AgentRun:
        with self.store.atomic():
            run = self.store.get_run(workspace_id, run_id)
            self._version(run, expected_version)
            if run.status is not AgentRunStatus.WAITING:
                raise InvariantViolation("resume_requires_waiting_run")
            if self.clock.now() >= run.deadline:
                return self._failure(workspace_id, run_id, "deadline_exceeded")
            if context.required_keys != run.context.required_keys:
                raise InvariantViolation("resume_cannot_change_acceptance_contract")
            changed = run.evolve(
                at=self.clock.now(), status=AgentRunStatus.RUNNING, context=context
            )
            # WAITING -> WAITING is intentionally illegal, use the explicit resume target.
            snapshot = self._parents(changed, waiting=True)
            self.domain.resume_execution(snapshot.execution.id, snapshot.execution.version)
            observation = Observation(
                self.ids.observation_id(),
                run.id,
                workspace_id,
                ObservationKind.CONTEXT_RECEIVED,
                "approved_context_supplied",
                provenance="caller",
                trust="caller_supplied_data",
            )
            self.store.append_observation(observation)
            state = replace(
                run.working_state,
                missing_fields=(),
                observations=(*run.working_state.observations, observation)[
                    -run.limits.recent_observations :
                ],
            )
            updated = run.evolve(
                at=self.clock.now(),
                status=AgentRunStatus.RUNNING,
                working_state=state,
                context=context,
            )
            self._save(run, updated, EventType.AGENT_RUN_RESUMED)
            self._event(
                updated, EventType.OBSERVATION_RECORDED, (("observation_id", str(observation.id)),)
            )
            return updated

    def cancel(
        self,
        workspace_id: WorkspaceId,
        run_id: AgentRunId,
        expected_version: Version,
    ) -> AgentRun:
        with self.store.atomic():
            run = self.store.get_run(workspace_id, run_id)
            self._version(run, expected_version)
            if run.status not in (AgentRunStatus.RUNNING, AgentRunStatus.WAITING):
                raise InvariantViolation("terminal_run_cannot_cancel")
            return self._failure(workspace_id, run_id, "cancelled", cancelled=True)

    def _deadline(self, run: AgentRun) -> None:
        if self.clock.now() >= run.deadline:
            raise ModelFailure("deadline_exceeded")

    def _failure(
        self,
        workspace_id: WorkspaceId,
        run_id: AgentRunId,
        code: str,
        *,
        cancelled: bool = False,
    ) -> AgentRun:
        with self.store.atomic():
            run = self.store.get_run(workspace_id, run_id)
            if run.status not in (AgentRunStatus.RUNNING, AgentRunStatus.WAITING):
                return run
            attempt = self.store.domain.get_task_attempt(run.task_attempt_id)
            execution = self.store.domain.get_execution(run.execution_id)
            task = self.store.domain.get_task(run.task_id)
            cancelled = (
                cancelled
                or execution.status is ExecutionStatus.CANCELLED
                or task.status is TaskStatus.CANCELLED
            )
            if attempt.status is TaskAttemptStatus.RUNNING:
                if cancelled:
                    self.domain.cancel_task_attempt(attempt.id, attempt.version)
                else:
                    self.domain.fail_task_attempt(attempt.id, attempt.version, code)
            if task.status is TaskStatus.IN_PROGRESS:
                if cancelled:
                    self.domain.cancel_task(task.id, task.version)
                else:
                    self.domain.ready_task(task.id, task.version)
            if execution.status in (ExecutionStatus.RUNNING, ExecutionStatus.WAITING):
                if cancelled:
                    self.domain.cancel_execution(execution.id, execution.version)
                else:
                    self.domain.fail_execution(execution.id, execution.version, code)
            observation = Observation(
                self.ids.observation_id(),
                run.id,
                workspace_id,
                ObservationKind.VALIDATION_ERROR,
                code,
            )
            self.store.append_observation(observation)
            state = replace(
                run.working_state,
                invocation_pending=False,
                observations=(*run.working_state.observations, observation)[
                    -run.limits.recent_observations :
                ],
            )
            updated = run.evolve(
                at=self.clock.now(),
                status=AgentRunStatus.CANCELLED if cancelled else AgentRunStatus.FAILED,
                working_state=state,
                error_code=code,
            )
            self._save(
                run,
                updated,
                EventType.AGENT_RUN_CANCELLED if cancelled else EventType.AGENT_RUN_FAILED,
            )
            self._event(
                updated, EventType.OBSERVATION_RECORDED, (("observation_id", str(observation.id)),)
            )
            failure_type = (
                EventType.MODEL_INVOCATION_FAILED
                if code
                in {
                    "model_timeout",
                    "provider_unavailable",
                    "rate_limited",
                    "model_refused",
                }
                else EventType.MODEL_DECISION_REJECTED
            )
            self._event(updated, failure_type, (("error_code", code),))
            return updated

    def _save(self, previous: AgentRun, updated: AgentRun, event_type: EventType) -> None:
        transition = None
        if previous.status != updated.status:
            transition = StateTransition(
                self.ids.state_transition_id(),
                updated.workspace_id,
                SubjectType.AGENT_RUN,
                str(updated.id),
                previous.status.value,
                updated.status.value,
                event_type.value,
                previous.version,
                updated.version,
                self.clock.now(),
            )
        self.store.save_run(updated, previous.version, transition)
        self._event(updated, event_type)

    def _event(
        self,
        run: AgentRun,
        event_type: EventType,
        extra: tuple[tuple[str, str], ...] = (),
    ) -> None:
        metadata = (
            ("execution_id", str(run.execution_id)),
            ("task_id", str(run.task_id)),
            ("task_attempt_id", str(run.task_attempt_id)),
            ("agent_run_id", str(run.id)),
            ("agent_definition_id", str(run.definition_version.definition.id)),
            ("agent_definition_version", str(run.definition_version.version.value)),
            ("iteration", str(run.working_state.iteration)),
            ("model_name", run.definition_version.model_name),
            ("policy_version", run.policy_version),
            ("runtime_protocol", run.runtime_protocol),
            ("evaluator_version", run.evaluator_version),
            ("status", run.status.value),
        )
        self.store.append_event(
            Event(
                self.ids.event_id(),
                run.workspace_id,
                event_type,
                SubjectType.AGENT_RUN,
                str(run.id),
                run.version,
                self.clock.now(),
                (*metadata, *extra),
            )
        )
