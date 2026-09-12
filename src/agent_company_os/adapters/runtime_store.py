"""Runtime records sharing one rollback boundary with the in-memory domain store."""

from collections.abc import Iterator
from contextlib import contextmanager

from agent_company_os.adapters.in_memory import InMemoryDomainStore
from agent_company_os.domain.agent import (
    ActionId,
    AgentDefinitionId,
    AgentDefinitionVersion,
    AgentRun,
    AgentRunId,
    AgentRunStatus,
    Observation,
    ObservationId,
)
from agent_company_os.domain.decisions import Action
from agent_company_os.domain.errors import (
    EntityNotFound,
    InvariantViolation,
    VersionConflict,
    WorkspaceMismatch,
)
from agent_company_os.domain.events import Event
from agent_company_os.domain.governance import ActionIntentId, ApprovalPolicy, GovernedAction
from agent_company_os.domain.ids import TaskAttemptId, Version, WorkspaceId
from agent_company_os.domain.tools import (
    ToolInvocation,
    ToolInvocationId,
    ToolInvocationStatus,
    ToolReceipt,
    ToolReceiptId,
)
from agent_company_os.domain.transitions import StateTransition, SubjectType


class InMemoryRuntimeStore:
    def __init__(self, domain: InMemoryDomainStore) -> None:
        self.domain = domain
        self._definitions: dict[tuple[AgentDefinitionId, Version], AgentDefinitionVersion] = {}
        self._runs: dict[AgentRunId, AgentRun] = {}
        self._events: list[Event] = []
        self._actions: dict[ActionId, Action] = {}
        self._observations: dict[ObservationId, Observation] = {}
        self._transitions: list[StateTransition] = []
        self._tool_invocations: dict[ToolInvocationId, ToolInvocation] = {}
        self._tool_receipts: dict[ToolReceiptId, ToolReceipt] = {}
        self._approval_policies: dict[WorkspaceId, ApprovalPolicy] = {}
        self._governed: dict[ActionIntentId, GovernedAction] = {}

    @contextmanager
    def atomic(self) -> Iterator[None]:
        with self.domain.transaction():
            snapshot = (
                self._definitions.copy(),
                self._runs.copy(),
                self._events.copy(),
                self._actions.copy(),
                self._observations.copy(),
                self._transitions.copy(),
                self._tool_invocations.copy(),
                self._tool_receipts.copy(),
                self._approval_policies.copy(),
                self._governed.copy(),
            )
            try:
                yield
            except BaseException:
                (
                    self._definitions,
                    self._runs,
                    self._events,
                    self._actions,
                    self._observations,
                    self._transitions,
                    self._tool_invocations,
                    self._tool_receipts,
                    self._approval_policies,
                    self._governed,
                ) = snapshot
                raise

    def approval_policy(self, workspace_id: WorkspaceId) -> ApprovalPolicy | None:
        self.domain.get_workspace(workspace_id)
        return self._approval_policies.get(workspace_id)

    def publish_approval_policy(self, policy: ApprovalPolicy) -> None:
        with self.atomic():
            old = self.approval_policy(policy.workspace_id)
            if policy.version != (old.version.next() if old else Version(1)):
                raise InvariantViolation("approval_policy_version_sequence")
            self._approval_policies[policy.workspace_id] = policy

    def governed_actions(self, workspace_id: WorkspaceId) -> tuple[GovernedAction, ...]:
        self.domain.get_workspace(workspace_id)
        return tuple(g for g in self._governed.values() if g.intent.workspace_id == workspace_id)

    def governed_action(
        self, workspace_id: WorkspaceId, intent_id: ActionIntentId
    ) -> GovernedAction:
        try:
            record = self._governed[intent_id]
        except KeyError as error:
            raise EntityNotFound("ActionIntent", str(intent_id)) from error
        self._scope(workspace_id, record.intent.workspace_id)
        return record

    def save_governed_action(self, record: GovernedAction, expected: Version | None) -> None:
        with self.atomic():
            intent = record.intent
            run = self.get_run(intent.workspace_id, intent.run_id)
            action = self.action(intent.workspace_id, intent.action_id)
            if (
                action.run_id != run.id
                or intent.goal_id != run.goal_id
                or intent.task_id != run.task_id
                or intent.execution_id != run.execution_id
            ):
                raise InvariantViolation("governed_action_lineage")
            old = self._governed.get(intent.id)
            if old is None:
                if (
                    expected is not None
                    or record.version != Version(1)
                    or record.decisions
                    or record.cancelled
                    or record.invocation_id is not None
                    or record.consumed
                    or len(self.governed_actions(intent.workspace_id)) >= 200
                    or any(g.intent.action_id == intent.action_id for g in self._governed.values())
                ):
                    raise InvariantViolation("governed_action_initial_state")
            else:
                if old.version != expected:
                    raise InvariantViolation("governed_action_version_conflict")
                if (
                    intent != old.intent
                    or record.request != old.request
                    or record.version != old.version.next()
                    or record.decisions[: len(old.decisions)] != old.decisions
                    or len(record.decisions) > len(old.decisions) + 1
                    or len(record.decisions) > 2
                    or old.cancelled
                    and not record.cancelled
                    or old.invocation_id is not None
                    and record.invocation_id != old.invocation_id
                    or old.consumed
                    and not record.consumed
                ):
                    raise InvariantViolation("governed_action_history_immutable")
            self._governed[intent.id] = record

    def publish(self, definition: AgentDefinitionVersion) -> None:
        with self.atomic():
            self.domain.get_workspace(definition.definition.workspace_id)
            key = (definition.definition.id, definition.version)
            if key in self._definitions:
                raise InvariantViolation("published_definition_is_immutable")
            lineage = [
                item
                for item in self._definitions.values()
                if item.definition.id == definition.definition.id
            ]
            if lineage and lineage[0].definition != definition.definition:
                raise InvariantViolation("definition_lineage_identity_is_immutable")
            if definition.version.value != len(lineage) + 1:
                raise InvariantViolation("definition_version_sequence")
            self._definitions[key] = definition

    def action(self, workspace_id: WorkspaceId, action_id: ActionId) -> Action:
        try:
            action = self._actions[action_id]
        except KeyError as error:
            raise EntityNotFound("Action", str(action_id)) from error
        self._scope(workspace_id, action.workspace_id)
        return action

    def tool_invocations(
        self, workspace_id: WorkspaceId, run_id: AgentRunId
    ) -> tuple[ToolInvocation, ...]:
        self.get_run(workspace_id, run_id)
        return tuple(item for item in self._tool_invocations.values() if item.run_id == run_id)

    def tool_receipts(
        self, workspace_id: WorkspaceId, run_id: AgentRunId
    ) -> tuple[ToolReceipt, ...]:
        self.get_run(workspace_id, run_id)
        return tuple(
            item for item in self._tool_receipts.values() if item.invocation.run_id == run_id
        )

    def add_tool_invocation(self, invocation: ToolInvocation) -> None:
        with self.atomic():
            run = self.get_run(invocation.workspace_id, invocation.run_id)
            action = self.action(invocation.workspace_id, invocation.action_id)
            if (
                action.run_id != run.id
                or invocation.task_attempt_id != run.task_attempt_id
                or invocation.execution_id != run.execution_id
                or invocation.run_version != run.version
                or invocation.tool_version.definition.workspace_id != run.workspace_id
                or invocation.tool_version.grant not in run.definition_version.allowed_tools
                or invocation.id in self._tool_invocations
                or invocation.version != Version(1)
                or invocation.status is not ToolInvocationStatus.RUNNING
                or any(item.action_id == action.id for item in self._tool_invocations.values())
            ):
                raise InvariantViolation("tool_invocation_binding_or_duplicate")
            self._tool_invocations[invocation.id] = invocation

    def finish_tool_invocation(self, receipt: ToolReceipt) -> None:
        with self.atomic():
            invocation = receipt.invocation
            self.get_run(invocation.workspace_id, invocation.run_id)
            previous = self._tool_invocations[invocation.id]
            if (
                receipt.id in self._tool_receipts
                or invocation.ended_at is None
                or previous.finish(invocation.ended_at, invocation.error_code) != invocation
            ):
                raise InvariantViolation("tool_receipt_append_only")
            self._tool_invocations[invocation.id] = invocation
            self._tool_receipts[receipt.id] = receipt

    def definition(
        self,
        workspace_id: WorkspaceId,
        definition_id: AgentDefinitionId,
        version: Version,
    ) -> AgentDefinitionVersion:
        try:
            definition = self._definitions[(definition_id, version)]
        except KeyError as error:
            raise EntityNotFound("AgentDefinitionVersion", str(definition_id)) from error
        self._scope(workspace_id, definition.definition.workspace_id)
        return definition

    def definitions(self, workspace_id: WorkspaceId) -> tuple[AgentDefinitionVersion, ...]:
        self.domain.get_workspace(workspace_id)
        return tuple(
            definition
            for definition in self._definitions.values()
            if definition.definition.workspace_id == workspace_id
        )

    @staticmethod
    def _scope(expected: WorkspaceId, actual: WorkspaceId) -> None:
        if expected != actual:
            raise WorkspaceMismatch("runtime_record", str(expected), str(actual))

    def get_run(self, workspace_id: WorkspaceId, run_id: AgentRunId) -> AgentRun:
        try:
            run = self._runs[run_id]
        except KeyError as error:
            raise EntityNotFound("AgentRun", str(run_id)) from error
        self._scope(workspace_id, run.workspace_id)
        return run

    def for_attempt(self, attempt_id: TaskAttemptId) -> tuple[AgentRun, ...]:
        return tuple(run for run in self._runs.values() if run.task_attempt_id == attempt_id)

    def for_definition(self, definition_id: AgentDefinitionId) -> tuple[AgentRun, ...]:
        return tuple(
            run
            for run in self._runs.values()
            if run.definition_version.definition.id == definition_id
        )

    def add_run(self, run: AgentRun) -> None:
        with self.atomic():
            if run.id in self._runs or self.for_attempt(run.task_attempt_id):
                raise InvariantViolation("one_agent_run_per_attempt")
            if any(
                item.execution_id == run.execution_id
                and item.status in (AgentRunStatus.RUNNING, AgentRunStatus.WAITING)
                for item in self._runs.values()
            ):
                raise InvariantViolation("one_active_agent_run_per_execution")
            attempt = self.domain.get_task_attempt(run.task_attempt_id)
            self._scope(run.workspace_id, attempt.workspace_id)
            definition = self.definition(
                run.workspace_id,
                run.definition_version.definition.id,
                run.definition_version.version,
            )
            if definition != run.definition_version or attempt.execution_id != run.execution_id:
                raise InvariantViolation("run_binding")
            if run.version != Version(1) or run.status is not AgentRunStatus.RUNNING:
                raise InvariantViolation("initial_run_state")
            self._runs[run.id] = run

    def save_run(
        self,
        run: AgentRun,
        expected_version: Version,
        transition: StateTransition | None,
    ) -> None:
        with self.atomic():
            previous = self.get_run(run.workspace_id, run.id)
            if previous.version != expected_version:
                raise VersionConflict(
                    "AgentRun", str(run.id), expected_version.value, previous.version.value
                )
            # Reapply through the domain method: terminal history and immutable bindings survive.
            candidate = previous.evolve(
                at=run.ended_at or run.created_at,
                status=run.status,
                working_state=run.working_state,
                context=run.context,
                error_code=run.error_code,
                result=run.result,
            )
            if candidate != run:
                raise InvariantViolation("run_mutation_contract")
            if (previous.status != run.status) != (transition is not None):
                raise InvariantViolation("run_transition_required")
            if transition is not None:
                if (
                    transition.subject_id != str(run.id)
                    or transition.workspace_id != run.workspace_id
                    or transition.subject_type is not SubjectType.AGENT_RUN
                    or transition.from_version != previous.version
                    or transition.to_version != run.version
                    or transition.previous_status != previous.status
                    or transition.new_status != run.status
                ):
                    raise InvariantViolation("run_transition_matches")
                self._transitions.append(transition)
            self._runs[run.id] = run

    def append_event(self, event: Event) -> None:
        run = self.get_run(event.workspace_id, AgentRunId(event.subject_id))
        if (
            event.entity_version != run.version
            or event.subject_type is not SubjectType.AGENT_RUN
            or any(old.id == event.id for old in self._events)
        ):
            raise InvariantViolation("runtime_event_binding")
        self._events.append(event)

    def append_action(self, action: Action) -> None:
        self.get_run(action.workspace_id, action.run_id)
        if action.id in self._actions:
            raise InvariantViolation("action_append_only")
        self._actions[action.id] = action

    def append_observation(self, observation: Observation) -> None:
        self.get_run(observation.workspace_id, observation.run_id)
        if observation.id in self._observations:
            raise InvariantViolation("observation_append_only")
        if observation.action_id is not None:
            action = self._actions[observation.action_id]
            if (
                action.run_id != observation.run_id
                or action.workspace_id != observation.workspace_id
            ):
                raise InvariantViolation("observation_action_binding")
        self._observations[observation.id] = observation

    def events(self, workspace_id: WorkspaceId) -> tuple[Event, ...]:
        return tuple(event for event in self._events if event.workspace_id == workspace_id)

    def transitions(self, workspace_id: WorkspaceId) -> tuple[StateTransition, ...]:
        return tuple(item for item in self._transitions if item.workspace_id == workspace_id)

    def actions(self, workspace_id: WorkspaceId) -> tuple[Action, ...]:
        return tuple(item for item in self._actions.values() if item.workspace_id == workspace_id)

    def observations(self, workspace_id: WorkspaceId) -> tuple[Observation, ...]:
        return tuple(
            item for item in self._observations.values() if item.workspace_id == workspace_id
        )
