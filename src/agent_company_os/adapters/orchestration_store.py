"""In-process orchestration history sharing the runtime transaction boundary."""

from collections.abc import Iterator
from contextlib import contextmanager

from agent_company_os.domain.errors import (
    EntityNotFound,
    InvariantViolation,
    VersionConflict,
    WorkspaceMismatch,
)
from agent_company_os.domain.events import Event
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.orchestration import (
    Delegation,
    DelegationAttempt,
    DelegationId,
    OrchestrationPlanId,
    OrchestrationRun,
    OrchestrationRunId,
    PlanMaterialization,
    PlanVersion,
)
from agent_company_os.domain.transitions import SubjectType
from agent_company_os.ports.runtime_store import RuntimeStore


class InMemoryOrchestrationStore:
    def __init__(self, runtime: RuntimeStore) -> None:
        self.runtime = runtime
        self._runs: dict[OrchestrationRunId, OrchestrationRun] = {}
        self._plans: dict[tuple[OrchestrationPlanId, Version], PlanVersion] = {}
        self._materializations: dict[tuple[OrchestrationPlanId, Version], PlanMaterialization] = {}
        self._delegations: dict[DelegationId, Delegation] = {}
        self._attempts: list[DelegationAttempt] = []
        self._events: list[Event] = []

    @contextmanager
    def atomic(self) -> Iterator[None]:
        with self.runtime.atomic():
            snapshot = (
                self._runs.copy(),
                self._plans.copy(),
                self._materializations.copy(),
                self._delegations.copy(),
                self._attempts.copy(),
                self._events.copy(),
            )
            try:
                yield
            except BaseException:
                (
                    self._runs,
                    self._plans,
                    self._materializations,
                    self._delegations,
                    self._attempts,
                    self._events,
                ) = snapshot
                raise

    @staticmethod
    def _scope(expected: WorkspaceId, actual: WorkspaceId, name: str) -> None:
        if expected != actual:
            raise WorkspaceMismatch(name, str(expected), str(actual))

    def add_run(self, run: OrchestrationRun) -> None:
        with self.atomic():
            goal = self.runtime.domain.get_goal(run.goal_id)
            self._scope(run.workspace_id, goal.workspace_id, "OrchestrationRun")
            if run.id in self._runs or run.version != Version(1):
                raise InvariantViolation("orchestration_run_identity")
            self._runs[run.id] = run

    def run(self, workspace_id: WorkspaceId, run_id: OrchestrationRunId) -> OrchestrationRun:
        try:
            run = self._runs[run_id]
        except KeyError as error:
            raise EntityNotFound("OrchestrationRun", str(run_id)) from error
        self._scope(workspace_id, run.workspace_id, "OrchestrationRun")
        return run

    def save_run(self, run: OrchestrationRun, expected: Version) -> None:
        with self.atomic():
            previous = self.run(run.workspace_id, run.id)
            if previous.version != expected:
                raise VersionConflict(
                    "OrchestrationRun", str(run.id), expected.value, previous.version.value
                )
            if run.version != previous.version.next():
                raise InvariantViolation("orchestration_run_version_increment")
            self._runs[run.id] = run

    def add_plan(self, plan: PlanVersion) -> None:
        with self.atomic():
            run = self.run(plan.workspace_id, plan.orchestration_run_id)
            key = (plan.id, plan.version)
            lineage = sorted(
                (item for (plan_id, _), item in self._plans.items() if plan_id == plan.id),
                key=lambda item: item.version.value,
            )
            if (
                key in self._plans
                or run.goal_id != plan.goal_id
                or plan.version.value != len(lineage) + 1
                or lineage
                and any(
                    item.workspace_id != plan.workspace_id
                    or item.goal_id != plan.goal_id
                    or item.orchestration_run_id != plan.orchestration_run_id
                    for item in lineage
                )
            ):
                raise InvariantViolation("orchestration_plan_lineage")
            self._plans[key] = plan

    def plan(
        self, workspace_id: WorkspaceId, plan_id: OrchestrationPlanId, version: Version
    ) -> PlanVersion:
        try:
            plan = self._plans[(plan_id, version)]
        except KeyError as error:
            raise EntityNotFound("PlanVersion", f"{plan_id}@{version.value}") from error
        self._scope(workspace_id, plan.workspace_id, "PlanVersion")
        return plan

    def plans(
        self, workspace_id: WorkspaceId, run_id: OrchestrationRunId
    ) -> tuple[PlanVersion, ...]:
        self.run(workspace_id, run_id)
        return tuple(
            sorted(
                (item for item in self._plans.values() if item.orchestration_run_id == run_id),
                key=lambda item: item.version.value,
            )
        )

    def add_materialization(self, materialization: PlanMaterialization) -> None:
        with self.atomic():
            plan = self.plan(
                materialization.workspace_id,
                materialization.plan_id,
                materialization.plan_version,
            )
            key = (materialization.plan_id, materialization.plan_version)
            if (
                key in self._materializations
                or plan.orchestration_run_id != materialization.orchestration_run_id
            ):
                raise InvariantViolation("plan_materialization_once")
            for lineage in materialization.tasks:
                task = self.runtime.domain.get_task(lineage.task_id)
                if (
                    task.workspace_id != materialization.workspace_id
                    or task.goal_id != plan.goal_id
                ):
                    raise InvariantViolation("materialized_task_binding")
            self._materializations[key] = materialization

    def materialization(
        self, workspace_id: WorkspaceId, plan_id: OrchestrationPlanId, version: Version
    ) -> PlanMaterialization:
        self.plan(workspace_id, plan_id, version)
        try:
            return self._materializations[(plan_id, version)]
        except KeyError as error:
            raise EntityNotFound("PlanMaterialization", f"{plan_id}@{version.value}") from error

    def add_delegation(self, delegation: Delegation) -> None:
        with self.atomic():
            run = self.run(delegation.workspace_id, delegation.orchestration_run_id)
            plan = self.plan(delegation.workspace_id, delegation.plan_id, delegation.plan_version)
            materialization = self.materialization(
                delegation.workspace_id, delegation.plan_id, delegation.plan_version
            )
            definition = self.runtime.definition(
                delegation.workspace_id,
                delegation.agent_definition_id,
                delegation.agent_definition_version,
            )
            if (
                delegation.id in self._delegations
                or run.id != plan.orchestration_run_id
                or not any(
                    item.planned_task_id == delegation.planned_task_id
                    and item.task_id == delegation.task_id
                    for item in materialization.tasks
                )
                or definition.definition.workspace_id != delegation.workspace_id
            ):
                raise InvariantViolation("delegation_binding")
            self._delegations[delegation.id] = delegation

    def delegation(self, workspace_id: WorkspaceId, delegation_id: DelegationId) -> Delegation:
        try:
            delegation = self._delegations[delegation_id]
        except KeyError as error:
            raise EntityNotFound("Delegation", str(delegation_id)) from error
        self._scope(workspace_id, delegation.workspace_id, "Delegation")
        return delegation

    def delegations(
        self, workspace_id: WorkspaceId, run_id: OrchestrationRunId
    ) -> tuple[Delegation, ...]:
        self.run(workspace_id, run_id)
        return tuple(
            item for item in self._delegations.values() if item.orchestration_run_id == run_id
        )

    def add_attempt(self, workspace_id: WorkspaceId, attempt: DelegationAttempt) -> None:
        with self.atomic():
            delegation = self.delegation(workspace_id, attempt.delegation_id)
            run = self.runtime.get_run(workspace_id, attempt.agent_run_id)
            if (
                any(old.agent_run_id == attempt.agent_run_id for old in self._attempts)
                or run.task_id != delegation.task_id
                or run.task_attempt_id != attempt.task_attempt_id
                or run.execution_id != attempt.execution_id
                or run.definition_version.definition.id != delegation.agent_definition_id
                or run.definition_version.version != delegation.agent_definition_version
            ):
                raise InvariantViolation("delegation_attempt_binding")
            self._attempts.append(attempt)

    def attempts(
        self, workspace_id: WorkspaceId, delegation_id: DelegationId
    ) -> tuple[DelegationAttempt, ...]:
        self.delegation(workspace_id, delegation_id)
        return tuple(item for item in self._attempts if item.delegation_id == delegation_id)

    def append_event(self, event: Event) -> None:
        if event.subject_type is SubjectType.ORCHESTRATION_RUN:
            entity_version = self.run(
                event.workspace_id, OrchestrationRunId(event.subject_id)
            ).version
        elif event.subject_type is SubjectType.ORCHESTRATION_PLAN:
            entity_version = event.entity_version
            self.plan(event.workspace_id, OrchestrationPlanId(event.subject_id), entity_version)
        elif event.subject_type is SubjectType.DELEGATION:
            entity_version = self.delegation(
                event.workspace_id, DelegationId(event.subject_id)
            ).version
        else:
            raise InvariantViolation("orchestration_event_subject")
        if event.entity_version != entity_version or any(
            old.id == event.id for old in self._events
        ):
            raise InvariantViolation("orchestration_event_binding")
        self._events.append(event)

    def events(self, workspace_id: WorkspaceId) -> tuple[Event, ...]:
        self.runtime.domain.get_workspace(workspace_id)
        return tuple(event for event in self._events if event.workspace_id == workspace_id)
