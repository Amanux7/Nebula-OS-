"""Bounded coordination over canonical Tasks and the existing Agent Runtime."""

from __future__ import annotations

import asyncio

from agent_company_os.application.runtime import AgentRuntimeService
from agent_company_os.application.service import (
    CreateExecutionCommand,
    CreateTaskAttemptCommand,
    CreateTaskCommand,
    DomainService,
)
from agent_company_os.domain.agent import (
    AgentDefinitionVersion,
    AgentRun,
    AgentRunStatus,
    Fact,
    SourceText,
    SuppliedContext,
)
from agent_company_os.domain.errors import (
    DomainError,
    EntityNotFound,
    InvariantViolation,
    VersionConflict,
)
from agent_company_os.domain.events import Event, EventType
from agent_company_os.domain.execution import ExecutionStatus
from agent_company_os.domain.goal import GoalStatus
from agent_company_os.domain.governance import ActionIntentId
from agent_company_os.domain.ids import GoalId, TaskId, Version, WorkspaceId
from agent_company_os.domain.orchestration import (
    AgentCatalogItem,
    AgentRequirements,
    Delegation,
    DelegationAttempt,
    DelegationId,
    GoalResultDraft,
    MaterializedTask,
    OrchestrationPolicy,
    OrchestrationRequest,
    OrchestrationRun,
    OrchestrationRunId,
    OrchestrationStatus,
    PlanMaterialization,
    PlanProposal,
    PlanVersion,
    TaskResultReference,
)
from agent_company_os.domain.organization import RegistryQuery, RouteKind
from agent_company_os.domain.organization_ids import DepartmentId
from agent_company_os.domain.plan_validation import validate_plan
from agent_company_os.domain.task import Task, TaskStatus
from agent_company_os.domain.transitions import SubjectType
from agent_company_os.ports.clock import Clock
from agent_company_os.ports.ids import IdGenerator
from agent_company_os.ports.orchestration import (
    AgentSelector,
    OrchestrationStore,
    OrchestrationStrategyPort,
    ResultAggregator,
)
from agent_company_os.ports.organization import AgentRegistryPort


class OrchestrationService:
    def __init__(
        self,
        store: OrchestrationStore,
        strategy: OrchestrationStrategyPort,
        selector: AgentSelector,
        aggregator: ResultAggregator,
        runtime: AgentRuntimeService,
        clock: Clock,
        ids: IdGenerator,
        registry: AgentRegistryPort | None = None,
    ) -> None:
        self.store, self.strategy, self.selector = store, strategy, selector
        self.aggregator, self.runtime = aggregator, runtime
        self.clock, self.ids = clock, ids
        self.registry = registry
        self.domain = DomainService(store.runtime.domain, clock, ids)

    def definitions_for_policy(
        self, workspace_id: WorkspaceId, policy: OrchestrationPolicy
    ) -> tuple[AgentDefinitionVersion, ...]:
        latest: dict[object, AgentDefinitionVersion] = {}
        for definition in self.store.runtime.definitions(workspace_id):
            current = latest.get(definition.definition.id)
            if current is None or definition.version > current.version:
                latest[definition.definition.id] = definition
        return tuple(
            sorted(
                (
                    item
                    for item in latest.values()
                    if item.enabled
                    and (
                        not policy.allowed_agent_ids
                        or item.definition.id in policy.allowed_agent_ids
                    )
                    and (not policy.allowed_roles or item.role in policy.allowed_roles)
                ),
                key=lambda item: str(item.definition.id),
            )
        )

    @staticmethod
    def _catalog(definitions: tuple[AgentDefinitionVersion, ...]) -> tuple[AgentCatalogItem, ...]:
        return tuple(
            AgentCatalogItem(
                item.definition.id,
                item.version,
                item.definition.workspace_id,
                item.role,
                item.capabilities,
                tuple(grant.tool_id for grant in item.allowed_tools),
                item.knowledge_scope.source_ids,
                item.memory_access.scopes,
                item.autonomy_ceiling,
                item.capability_ids,
            )
            for item in definitions
        )

    def candidates(
        self, run: OrchestrationRun, requirements: AgentRequirements
    ) -> tuple[AgentDefinitionVersion, ...]:
        if run.organization is None:
            if (
                requirements.capability_ids
                or requirements.required_department
                or requirements.preferred_department
                or requirements.organizational_role
                or run.source_department
            ):
                raise InvariantViolation("organization_required")
            return self.definitions_for_policy(run.workspace_id, run.policy)
        if self.registry is None:
            raise InvariantViolation("organization_registry_required")
        candidates = self.registry.query(
            run.workspace_id,
            run.organization,
            RegistryQuery(
                requirements.required_department,
                requirements.organizational_role,
                requirements.capability_ids,
            ),
        )
        return tuple(
            a
            for a in candidates
            if (not run.policy.allowed_agent_ids or a.definition.id in run.policy.allowed_agent_ids)
            and (not run.policy.allowed_roles or a.role in run.policy.allowed_roles)
        )

    def select_agent(
        self,
        run: OrchestrationRun,
        requirements: AgentRequirements,
        candidates: tuple[AgentDefinitionVersion, ...] | None = None,
        excluded: tuple[AgentDefinitionVersion, ...] = (),
        sources: tuple[AgentDefinitionVersion, ...] = (),
        route_kind: RouteKind = RouteKind.DELEGATE,
    ) -> AgentDefinitionVersion:
        eligible = self.candidates(run, requirements)
        # Legacy retries may use historical exact versions; organization runs are pinned.
        if candidates is not None:
            eligible = tuple(
                a
                for a in candidates
                if (run.organization is None or a in eligible)
                and (
                    not run.policy.allowed_agent_ids
                    or a.definition.id in run.policy.allowed_agent_ids
                )
                and (not run.policy.allowed_roles or a.role in run.policy.allowed_roles)
            )
        if run.source_department and run.organization and self.registry:
            routed = []
            for a in eligible:
                try:
                    self.registry.require_route(
                        run.workspace_id,
                        run.organization,
                        run.source_department,
                        a,
                        RouteKind.DELEGATE,
                    )
                except InvariantViolation:
                    continue
                routed.append(a)
            eligible = tuple(routed)
        if sources and run.organization:
            routed_candidates = []
            for candidate in eligible:
                try:
                    for source in sources:
                        self.require_organization_route(run, source, candidate, route_kind)
                        if route_kind is RouteKind.HANDOFF:
                            self.require_organization_route(
                                run, source, candidate, RouteKind.DELEGATE
                            )
                except InvariantViolation:
                    continue
                routed_candidates.append(candidate)
            eligible = tuple(routed_candidates)
        if requirements.preferred_department and run.organization and self.registry:
            preferred = self.registry.query(
                run.workspace_id, run.organization, RegistryQuery(requirements.preferred_department)
            )
            try:
                return self.selector.select(
                    run.workspace_id,
                    requirements,
                    tuple(a for a in eligible if a in preferred),
                    excluded,
                )
            except InvariantViolation as error:
                if error.details.get("rule") != "no_eligible_agent":
                    raise
        return self.selector.select(run.workspace_id, requirements, eligible, excluded)

    def require_organization_route(
        self,
        run: OrchestrationRun,
        source: AgentDefinitionVersion,
        target: AgentDefinitionVersion,
        kind: RouteKind,
    ) -> None:
        if run.organization is not None:
            if self.registry is None:
                raise InvariantViolation("organization_registry_required")
            self.registry.require_route(run.workspace_id, run.organization, source, target, kind)

    def candidates_for_task(
        self, run: OrchestrationRun, task_id: TaskId
    ) -> tuple[AgentDefinitionVersion, ...]:
        plan, materialization = self._current(run)
        lineage = next((m for m in materialization.tasks if m.task_id == task_id), None)
        if lineage is None:
            raise InvariantViolation("handoff_task_lineage")
        requirements = next(
            p.requirements for p in plan.proposal.tasks if p.id == lineage.planned_task_id
        )
        result = []
        for candidate in self.candidates(run, requirements):
            try:
                self.select_agent(run, requirements, (candidate,))
            except InvariantViolation:
                continue
            result.append(candidate)
        return tuple(result)

    async def start(
        self,
        workspace_id: WorkspaceId,
        goal_id: GoalId,
        policy: OrchestrationPolicy | None = None,
        source_department: DepartmentId | None = None,
    ) -> OrchestrationRun:
        policy = policy or OrchestrationPolicy()
        with self.store.atomic():
            goal = self.store.runtime.domain.get_goal(goal_id)
            if goal.workspace_id != workspace_id or goal.status is not GoalStatus.ACTIVE:
                raise InvariantViolation("orchestration_requires_active_scoped_goal")
            run = OrchestrationRun(
                self.ids.orchestration_run_id(),
                workspace_id,
                goal_id,
                self.strategy.strategy_id,
                self.strategy.strategy_version,
                policy,
                self.clock.now(),
                organization=self.registry.capture(workspace_id) if self.registry else None,
                source_department=source_department,
            )
            self.store.add_run(run)
            self._event(run, EventType.ORCHESTRATION_STARTED)
            request = OrchestrationRequest(
                workspace_id,
                goal.id,
                goal.version,
                goal.objective,
                goal.constraints,
                self._catalog(self.candidates(run, AgentRequirements())),
                policy,
            )
        try:
            proposal = await asyncio.wait_for(
                self.strategy.plan(request), timeout=policy.planner_seconds
            )
            return self._accept_plan(run.id, request, proposal, replan=False)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            with self.store.atomic():
                current = self.store.run(workspace_id, run.id)
                failed = current.evolve(
                    at=self.clock.now(),
                    status=OrchestrationStatus.FAILED,
                    escalation_reason="planner_failed",
                )
                self.store.save_run(failed, current.version)
                self._event(
                    failed,
                    EventType.PLAN_REJECTED,
                    (("reason", getattr(error, "code", "planner_failed")),),
                )
                return failed

    def _accept_plan(
        self,
        run_id: OrchestrationRunId,
        request: OrchestrationRequest,
        proposal: PlanProposal,
        *,
        replan: bool,
    ) -> OrchestrationRun:
        with self.store.atomic():
            run = self.store.run(request.workspace_id, run_id)
            goal = self.store.runtime.domain.get_goal(run.goal_id)
            if goal.version != request.goal_version or goal.status is not GoalStatus.ACTIVE:
                raise VersionConflict(
                    "Goal", str(goal.id), request.goal_version.value, goal.version.value
                )
            validate_plan(request, proposal)
            for task in proposal.tasks:
                self.select_agent(run, task.requirements)
            prior = self.store.plans(run.workspace_id, run.id)
            plan_id = run.plan_id or self.ids.orchestration_plan_id()
            version = Version(len(prior) + 1)
            if replan and prior:
                old_ids = {task.id for task in prior[-1].proposal.tasks}
                if not old_ids <= {task.id for task in proposal.tasks}:
                    raise InvariantViolation("replan_cannot_orphan_canonical_tasks")
            plan = PlanVersion(
                plan_id,
                run.workspace_id,
                run.goal_id,
                run.id,
                version,
                self.strategy.strategy_id,
                self.strategy.strategy_version,
                run.policy.version,
                goal.version,
                proposal,
                self.clock.now(),
            )
            self.store.add_plan(plan)
            updated = run.evolve(
                at=self.clock.now(),
                status=OrchestrationStatus.RUNNING,
                plan_id=plan.id,
                plan_version=plan.version,
                replan_delta=1 if replan else 0,
            )
            self.store.save_run(updated, run.version)
            self._plan_event(plan, EventType.PLAN_PROPOSED)
            self._plan_event(plan, EventType.PLAN_ACCEPTED)
            if replan:
                self._event(updated, EventType.REPLAN_COMPLETED)
            return updated

    async def replan(
        self, workspace_id: WorkspaceId, run_id: OrchestrationRunId, expected: Version
    ) -> OrchestrationRun:
        with self.store.atomic():
            run = self.store.run(workspace_id, run_id)
            self._version(run, expected)
            if run.status not in {OrchestrationStatus.RUNNING, OrchestrationStatus.WAITING}:
                raise InvariantViolation("orchestration_not_replannable")
            if run.agent_run_count + run.replan_count >= run.policy.max_iterations:
                raise InvariantViolation("orchestration_iteration_limit")
            if run.replan_count >= run.policy.max_replans:
                waiting = run.evolve(
                    at=self.clock.now(),
                    status=OrchestrationStatus.WAITING,
                    escalation_reason="replan_exhausted",
                )
                self.store.save_run(waiting, run.version)
                self._event(waiting, EventType.ORCHESTRATION_FAILED)
                return waiting
            goal = self.store.runtime.domain.get_goal(run.goal_id)
            planning = run.evolve(at=self.clock.now(), status=OrchestrationStatus.PLANNING)
            self.store.save_run(planning, run.version)
            self._event(planning, EventType.REPLAN_REQUESTED)
            request = OrchestrationRequest(
                workspace_id,
                goal.id,
                goal.version,
                goal.objective,
                goal.constraints,
                self._catalog(self.candidates(run, AgentRequirements())),
                run.policy,
            )
        try:
            proposal = await asyncio.wait_for(
                self.strategy.plan(request), timeout=run.policy.planner_seconds
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            with self.store.atomic():
                current = self.store.run(workspace_id, run_id)
                waiting = current.evolve(
                    at=self.clock.now(),
                    status=OrchestrationStatus.WAITING,
                    escalation_reason="planner_failed",
                )
                self.store.save_run(waiting, current.version)
                self._event(waiting, EventType.PLAN_REJECTED, (("reason", str(error)[:128]),))
                return waiting
        try:
            return self._accept_plan(run_id, request, proposal, replan=True)
        except DomainError as error:
            with self.store.atomic():
                current = self.store.run(workspace_id, run_id)
                waiting = current.evolve(
                    at=self.clock.now(),
                    status=OrchestrationStatus.WAITING,
                    escalation_reason="plan_rejected",
                )
                self.store.save_run(waiting, current.version)
                self._event(waiting, EventType.PLAN_REJECTED, (("reason", error.code),))
                return waiting

    def materialize(
        self, workspace_id: WorkspaceId, run_id: OrchestrationRunId, expected: Version
    ) -> PlanMaterialization:
        with self.store.atomic():
            run = self.store.run(workspace_id, run_id)
            self._version(run, expected)
            if (
                run.status is not OrchestrationStatus.RUNNING
                or run.plan_id is None
                or run.current_plan_version is None
            ):
                raise InvariantViolation("orchestration_plan_not_ready")
            plan = self.store.plan(workspace_id, run.plan_id, run.current_plan_version)
            goal = self.store.runtime.domain.get_goal(run.goal_id)
            if goal.version != plan.goal_version or goal.status is not GoalStatus.ACTIVE:
                raise VersionConflict(
                    "Goal", str(goal.id), plan.goal_version.value, goal.version.value
                )
            try:
                return self.store.materialization(workspace_id, plan.id, plan.version)
            except EntityNotFound:
                pass
            prior_lineage: dict[str, TaskId] = {}
            for prior in self.store.plans(workspace_id, run.id)[:-1]:
                try:
                    materialized = self.store.materialization(workspace_id, prior.id, prior.version)
                except EntityNotFound:
                    continue
                prior_lineage.update(
                    (item.planned_task_id, item.task_id) for item in materialized.tasks
                )
            lineages = []
            for planned in plan.proposal.tasks:
                task_id = prior_lineage.get(planned.id)
                if task_id is None:
                    task = self.domain.create_task(
                        CreateTaskCommand(
                            workspace_id,
                            run.goal_id,
                            planned.title,
                            planned.acceptance_criteria,
                        )
                    )
                    task_id = task.id
                lineages.append(MaterializedTask(plan.id, plan.version, planned.id, task_id))
            execution_id = run.execution_id
            if execution_id is None:
                execution = self.domain.create_execution(
                    CreateExecutionCommand(
                        workspace_id,
                        run.goal_id,
                        f"orchestration:{run.id}",
                        run.policy.max_agent_runs,
                    )
                )
                execution = self.domain.start_execution(execution.id, execution.version)
                execution_id = execution.id
            materialization = PlanMaterialization(
                workspace_id,
                run.id,
                plan.id,
                plan.version,
                tuple(lineages),
                self.clock.now(),
            )
            self.store.add_materialization(materialization)
            updated = run.evolve(at=self.clock.now(), execution_id=execution_id)
            self.store.save_run(updated, run.version)
            self._plan_event(plan, EventType.PLAN_MATERIALIZED)
            return materialization

    def _current(self, run: OrchestrationRun) -> tuple[PlanVersion, PlanMaterialization]:
        if run.plan_id is None or run.current_plan_version is None:
            raise InvariantViolation("orchestration_has_no_current_plan")
        return (
            self.store.plan(run.workspace_id, run.plan_id, run.current_plan_version),
            self.store.materialization(run.workspace_id, run.plan_id, run.current_plan_version),
        )

    def ready_tasks(
        self, workspace_id: WorkspaceId, run_id: OrchestrationRunId
    ) -> tuple[Task, ...]:
        run = self.store.run(workspace_id, run_id)
        if run.status is not OrchestrationStatus.RUNNING:
            return ()
        plan, materialization = self._current(run)
        by_planned = {item.planned_task_id: item.task_id for item in materialization.tasks}
        order = {task.id: index for index, task in enumerate(plan.proposal.tasks)}
        ready: list[tuple[int, int, str, Task]] = []
        for planned in plan.proposal.tasks:
            task = self.store.runtime.domain.get_task(by_planned[planned.id])
            dependencies = tuple(
                self.store.runtime.domain.get_task(by_planned[parent])
                for parent in planned.dependencies
            )
            if task.status in {TaskStatus.PROPOSED, TaskStatus.READY} and all(
                item.status is TaskStatus.COMPLETED for item in dependencies
            ):
                ready.append((planned.priority, order[planned.id], str(task.id), task))
        ready.sort(key=lambda item: item[:3])
        return tuple(item[3] for item in ready)

    def delegate(
        self,
        workspace_id: WorkspaceId,
        run_id: OrchestrationRunId,
        task_id: TaskId,
        expected: Version,
        *,
        mode: str = "initial",
        target_definition: AgentDefinitionVersion | None = None,
    ) -> Delegation | None:
        with self.store.atomic():
            run = self.store.run(workspace_id, run_id)
            self._version(run, expected)
            if task_id not in {task.id for task in self.ready_tasks(workspace_id, run_id)}:
                raise InvariantViolation("delegation_requires_ready_dependency_state")
            if run.agent_run_count + run.replan_count >= run.policy.max_iterations:
                raise InvariantViolation("orchestration_iteration_limit")
            plan, materialization = self._current(run)
            lineage = next(item for item in materialization.tasks if item.task_id == task_id)
            planned = next(
                item for item in plan.proposal.tasks if item.id == lineage.planned_task_id
            )
            previous = tuple(
                item
                for item in self.store.delegations(workspace_id, run_id)
                if item.task_id == task_id
            )
            active_delegations = 0
            for old in self.store.delegations(workspace_id, run_id):
                attempts = self.store.attempts(workspace_id, old.id)
                if not attempts or self.store.runtime.get_run(
                    workspace_id, attempts[-1].agent_run_id
                ).status in {
                    AgentRunStatus.RUNNING,
                    AgentRunStatus.WAITING,
                }:
                    active_delegations += 1
            if mode == "initial" and active_delegations >= run.policy.max_parallel_width:
                raise InvariantViolation("orchestration_parallel_width")
            if mode == "initial" and previous:
                if not self.store.attempts(workspace_id, previous[-1].id):
                    return previous[-1]
                raise InvariantViolation("task_already_delegated")
            definitions = self.candidates(run, planned.requirements)
            excluded: tuple[AgentDefinitionVersion, ...] = ()
            if mode == "retry":
                if not previous or previous[-1].retry_ordinal >= run.policy.max_retries_per_task:
                    raise InvariantViolation("orchestration_retry_limit")
                prior_attempts = self.store.attempts(workspace_id, previous[-1].id)
                if (
                    not prior_attempts
                    or self.store.runtime.get_run(
                        workspace_id, prior_attempts[-1].agent_run_id
                    ).status
                    is not AgentRunStatus.FAILED
                ):
                    raise InvariantViolation("retry_requires_failed_agent_run")
                definitions = (
                    self.store.runtime.definition(
                        workspace_id,
                        previous[-1].agent_definition_id,
                        previous[-1].agent_definition_version,
                    ),
                )
            elif mode == "redelegate":
                if (
                    not previous
                    or previous[-1].redelegation_ordinal >= run.policy.max_redelegations_per_task
                ):
                    raise InvariantViolation("orchestration_redelegation_limit")
                prior_attempts = self.store.attempts(workspace_id, previous[-1].id)
                if (
                    not prior_attempts
                    or self.store.runtime.get_run(
                        workspace_id, prior_attempts[-1].agent_run_id
                    ).status
                    is not AgentRunStatus.FAILED
                ):
                    raise InvariantViolation("redelegation_requires_failed_agent_run")
                excluded = tuple(
                    self.store.runtime.definition(
                        workspace_id, item.agent_definition_id, item.agent_definition_version
                    )
                    for item in previous
                )
            elif mode != "initial":
                raise InvariantViolation("delegation_mode")
            try:
                if target_definition is not None:
                    if mode != "redelegate":
                        raise InvariantViolation("target_definition_requires_redelegation")
                    definitions = (target_definition,)
                sources = []
                # Dataflow from predecessor Tasks is also an organizational route.
                for dependency in planned.dependencies:
                    source_task = next(
                        m.task_id for m in materialization.tasks if m.planned_task_id == dependency
                    )
                    source_delegations = tuple(
                        d
                        for d in self.store.delegations(workspace_id, run.id)
                        if d.task_id == source_task
                    )
                    if source_delegations:
                        source_assignment = source_delegations[-1]
                        source = self.store.runtime.definition(
                            workspace_id,
                            source_assignment.agent_definition_id,
                            source_assignment.agent_definition_version,
                        )
                        sources.append(source)
                if mode == "redelegate" and previous:
                    source = self.store.runtime.definition(
                        workspace_id,
                        previous[-1].agent_definition_id,
                        previous[-1].agent_definition_version,
                    )
                    sources.append(source)
                selected = self.select_agent(
                    run, planned.requirements, definitions, excluded, tuple(sources)
                )
            except InvariantViolation as error:
                if error.details.get("rule") != "no_eligible_agent":
                    raise
                waiting = run.evolve(
                    at=self.clock.now(),
                    status=OrchestrationStatus.WAITING,
                    escalation_reason="no_eligible_agent",
                )
                self.store.save_run(waiting, run.version)
                self._event(waiting, EventType.DELEGATION_REJECTED)
                return None
            delegation = Delegation(
                self.ids.delegation_id(),
                workspace_id,
                run.id,
                plan.id,
                plan.version,
                planned.id,
                task_id,
                selected.definition.id,
                selected.version,
                self.clock.now(),
                retry_ordinal=(
                    previous[-1].retry_ordinal + (1 if mode == "retry" else 0) if previous else 0
                ),
                redelegation_ordinal=(
                    previous[-1].redelegation_ordinal + (1 if mode == "redelegate" else 0)
                    if previous
                    else 0
                ),
            )
            self.store.add_delegation(delegation)
            self._delegation_event(delegation, EventType.TASK_DELEGATED, (("mode", mode),))
            return delegation

    def context_for_task(
        self,
        workspace_id: WorkspaceId,
        run_id: OrchestrationRunId,
        task_id: TaskId,
        required_keys: tuple[str, ...],
        supplied_facts: tuple[Fact, ...] = (),
        supplied_texts: tuple[SourceText, ...] = (),
    ) -> tuple[SuppliedContext, tuple[TaskResultReference, ...]]:
        run = self.store.run(workspace_id, run_id)
        plan, materialization = self._current(run)
        lineage = next(item for item in materialization.tasks if item.task_id == task_id)
        planned = next(item for item in plan.proposal.tasks if item.id == lineage.planned_task_id)
        by_planned = {item.planned_task_id: item.task_id for item in materialization.tasks}
        facts = list(supplied_facts)
        references = []
        for dependency in planned.dependencies:
            source_task_id = by_planned[dependency]
            source_delegations = tuple(
                item
                for item in self.store.delegations(workspace_id, run.id)
                if item.task_id == source_task_id
            )
            found = None
            for delegation in reversed(source_delegations):
                for attempt in reversed(self.store.attempts(workspace_id, delegation.id)):
                    agent_run = self.store.runtime.get_run(workspace_id, attempt.agent_run_id)
                    if (
                        agent_run.status is AgentRunStatus.SUCCEEDED
                        and agent_run.result is not None
                    ):
                        found = (attempt, agent_run)
                        break
                if found:
                    break
            if found is None:
                raise InvariantViolation("upstream_result_unavailable")
            attempt, agent_run = found
            result = agent_run.result
            if result is None:
                raise InvariantViolation("upstream_result_unavailable")
            reference = TaskResultReference(
                source_task_id,
                attempt.task_attempt_id,
                agent_run.id,
                agent_run.version,
                result.source_references,
            )
            references.append(reference)
            facts.extend(
                Fact(fact.key, fact.value, reference.reference) for fact in result.findings
            )
        if len(facts) > 50:
            raise InvariantViolation("downstream_context_fact_bound")
        return (
            SuppliedContext(workspace_id, task_id, required_keys, tuple(facts), supplied_texts),
            tuple(references),
        )

    async def execute(
        self,
        workspace_id: WorkspaceId,
        orchestration_run_id: OrchestrationRunId,
        delegation_id: DelegationId,
        expected: Version,
        context: SuppliedContext,
    ) -> AgentRun:
        with self.store.atomic():
            orchestration = self.store.run(workspace_id, orchestration_run_id)
            self._version(orchestration, expected)
            delegation = self.store.delegation(workspace_id, delegation_id)
            if (
                orchestration.status is not OrchestrationStatus.RUNNING
                or delegation.orchestration_run_id != orchestration.id
                or context.task_id != delegation.task_id
                or orchestration.agent_run_count >= orchestration.policy.max_agent_runs
            ):
                raise InvariantViolation("delegation_execution_binding_or_budget")
            task = self.store.runtime.domain.get_task(delegation.task_id)
            plan, materialization = self._current(orchestration)
            planned = next(p for p in plan.proposal.tasks if p.id == delegation.planned_task_id)
            exact = self.store.runtime.definition(
                workspace_id, delegation.agent_definition_id, delegation.agent_definition_version
            )
            self.select_agent(orchestration, planned.requirements, (exact,))
            if task not in self.ready_tasks(workspace_id, orchestration.id):
                raise InvariantViolation("delegation_task_not_ready")
            if task.status is TaskStatus.PROPOSED:
                task = self.domain.ready_task(task.id, task.version)
            task = self.domain.start_task(task.id, task.version)
            execution = (
                self.store.runtime.domain.get_execution(orchestration.execution_id)
                if orchestration.execution_id
                else None
            )
            if execution is None or execution.status in {
                ExecutionStatus.SUCCEEDED,
                ExecutionStatus.FAILED,
                ExecutionStatus.CANCELLED,
            }:
                replacement = self.domain.create_execution(
                    CreateExecutionCommand(
                        workspace_id,
                        orchestration.goal_id,
                        f"orchestration:{orchestration.id}",
                        orchestration.policy.max_agent_runs,
                        execution.id if execution else None,
                    )
                )
                execution = self.domain.start_execution(replacement.id, replacement.version)
                orchestration = orchestration.evolve(at=self.clock.now(), execution_id=execution.id)
                self.store.save_run(orchestration, expected)
            attempt = self.domain.create_task_attempt(
                CreateTaskAttemptCommand(workspace_id, task.id, execution.id)
            )
            attempt = self.domain.start_task_attempt(attempt.id, attempt.version)
            agent_run = self.runtime.start(
                workspace_id,
                delegation.agent_definition_id,
                delegation.agent_definition_version,
                attempt.id,
                context,
                organization_version=orchestration.organization.graph.version
                if orchestration.organization
                else None,
            )
            self.store.add_attempt(
                workspace_id,
                DelegationAttempt(delegation.id, execution.id, attempt.id, agent_run.id),
            )
            current = self.store.run(workspace_id, orchestration.id)
            counted = current.evolve(at=self.clock.now(), agent_run_delta=1)
            self.store.save_run(counted, current.version)
        result = await self.runtime.drive(workspace_id, agent_run.id, agent_run.version)
        return self._reconcile_result(workspace_id, orchestration_run_id, result)

    async def resume_delegation(
        self,
        workspace_id: WorkspaceId,
        orchestration_run_id: OrchestrationRunId,
        delegation_id: DelegationId,
        expected: Version,
        context: SuppliedContext,
        intent_id: ActionIntentId | None = None,
    ) -> AgentRun:
        """Resume a waiting child run and retain orchestration-level bookkeeping."""
        with self.store.atomic():
            orchestration = self.store.run(workspace_id, orchestration_run_id)
            self._version(orchestration, expected)
            delegation = self.store.delegation(workspace_id, delegation_id)
            attempts = self.store.attempts(workspace_id, delegation.id)
            if (
                orchestration.status is not OrchestrationStatus.WAITING
                or delegation.orchestration_run_id != orchestration.id
                or not attempts
                or context.task_id != delegation.task_id
            ):
                raise InvariantViolation("delegation_resume_binding")
            agent_run = self.store.runtime.get_run(workspace_id, attempts[-1].agent_run_id)
            if intent_id is not None:
                if context != agent_run.context:
                    raise InvariantViolation("approval_resume_cannot_change_context")
                resumed = agent_run
            else:
                resumed = self.runtime.resume(
                    workspace_id, agent_run.id, agent_run.version, context
                )
            running = orchestration.evolve(
                at=self.clock.now(),
                status=OrchestrationStatus.RUNNING,
                escalation_reason=None,
            )
            self.store.save_run(running, orchestration.version)
        try:
            result = (
                await self.runtime.resume_approval(
                    workspace_id, resumed.id, intent_id, resumed.version
                )
                if intent_id is not None
                else await self.runtime.drive(workspace_id, resumed.id, resumed.version)
            )
        except Exception:
            if intent_id is not None:
                with self.store.atomic():
                    current = self.store.run(workspace_id, orchestration_run_id)
                    if current.status is OrchestrationStatus.RUNNING:
                        waiting = current.evolve(
                            at=self.clock.now(),
                            status=OrchestrationStatus.WAITING,
                            escalation_reason="approval_revalidation_failed",
                        )
                        self.store.save_run(waiting, current.version)
            raise
        return self._reconcile_result(workspace_id, orchestration_run_id, result)

    def _reconcile_result(
        self,
        workspace_id: WorkspaceId,
        orchestration_run_id: OrchestrationRunId,
        result: AgentRun,
    ) -> AgentRun:
        with self.store.atomic():
            current = self.store.run(workspace_id, orchestration_run_id)
            failed = result.status is AgentRunStatus.FAILED
            status = current.status
            reason = None
            if result.status is AgentRunStatus.WAITING:
                status, reason = (
                    OrchestrationStatus.WAITING,
                    "approval_required"
                    if result.working_state.invocation_pending
                    else "required_context_missing",
                )
            elif failed and current.failed_attempt_count + 1 >= current.policy.max_failed_attempts:
                status, reason = OrchestrationStatus.WAITING, "failure_budget_exhausted"
            updated = current.evolve(
                at=self.clock.now(),
                status=status,
                failed_delta=1 if failed else 0,
                escalation_reason=reason,
            )
            self.store.save_run(updated, current.version)
            if result.status is AgentRunStatus.SUCCEEDED:
                draft = self.aggregate(workspace_id, orchestration_run_id)
                _, materialization = self._current(updated)
                all_materialized_complete = all(
                    self.store.runtime.domain.get_task(item.task_id).status is TaskStatus.COMPLETED
                    for item in materialization.tasks
                )
                if draft.complete and all_materialized_complete:
                    goal = self.store.runtime.domain.get_goal(current.goal_id)
                    self.domain.satisfy_goal(goal.id, goal.version)
                    completed = updated.evolve(
                        at=self.clock.now(), status=OrchestrationStatus.COMPLETED
                    )
                    self.store.save_run(completed, updated.version)
                    self._event(completed, EventType.ORCHESTRATION_COMPLETED)
            return result

    def aggregate(self, workspace_id: WorkspaceId, run_id: OrchestrationRunId) -> GoalResultDraft:
        run = self.store.run(workspace_id, run_id)
        plan, materialization = self._current(run)
        required = {item.id for item in plan.proposal.tasks if item.required}
        results = []
        for lineage in materialization.tasks:
            if lineage.planned_task_id not in required:
                continue
            for delegation in reversed(self.store.delegations(workspace_id, run.id)):
                if delegation.task_id != lineage.task_id:
                    continue
                for attempt in reversed(self.store.attempts(workspace_id, delegation.id)):
                    agent_run = self.store.runtime.get_run(workspace_id, attempt.agent_run_id)
                    if agent_run.status is AgentRunStatus.SUCCEEDED and agent_run.result:
                        results.append(
                            TaskResultReference(
                                lineage.task_id,
                                attempt.task_attempt_id,
                                agent_run.id,
                                agent_run.version,
                                agent_run.result.source_references,
                            )
                        )
                        break
                else:
                    continue
                break
        return self.aggregator.aggregate(run.goal_id, len(required), tuple(results))

    def cancel(
        self, workspace_id: WorkspaceId, run_id: OrchestrationRunId, expected: Version
    ) -> OrchestrationRun:
        with self.store.atomic():
            run = self.store.run(workspace_id, run_id)
            self._version(run, expected)
            if run.status in {
                OrchestrationStatus.COMPLETED,
                OrchestrationStatus.FAILED,
                OrchestrationStatus.CANCELLED,
            }:
                raise InvariantViolation("terminal_orchestration_cannot_cancel")
            for plan in self.store.plans(workspace_id, run.id):
                try:
                    materialization = self.store.materialization(
                        workspace_id, plan.id, plan.version
                    )
                except EntityNotFound:
                    continue
                for lineage in materialization.tasks:
                    task = self.store.runtime.domain.get_task(lineage.task_id)
                    if task.status in {TaskStatus.PROPOSED, TaskStatus.READY, TaskStatus.BLOCKED}:
                        self.domain.cancel_task(task.id, task.version)
            if run.execution_id:
                execution = self.store.runtime.domain.get_execution(run.execution_id)
                if execution.status in {ExecutionStatus.RUNNING, ExecutionStatus.WAITING}:
                    self.domain.cancel_execution(execution.id, execution.version)
            goal = self.store.runtime.domain.get_goal(run.goal_id)
            if goal.status is GoalStatus.ACTIVE:
                self.domain.cancel_goal(goal.id, goal.version)
            cancelled = run.evolve(at=self.clock.now(), status=OrchestrationStatus.CANCELLED)
            self.store.save_run(cancelled, run.version)
            self._event(cancelled, EventType.ORCHESTRATION_CANCELLED)
            return cancelled

    @staticmethod
    def _version(run: OrchestrationRun, expected: Version) -> None:
        if run.version != expected:
            raise VersionConflict(
                "OrchestrationRun", str(run.id), expected.value, run.version.value
            )

    def _event(
        self,
        run: OrchestrationRun,
        kind: EventType,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self.store.append_event(
            Event(
                self.ids.event_id(),
                run.workspace_id,
                kind,
                SubjectType.ORCHESTRATION_RUN,
                str(run.id),
                run.version,
                self.clock.now(),
                (
                    ("strategy_id", run.strategy_id),
                    (
                        "organization_graph_id",
                        str(run.organization.graph.graph_id) if run.organization else "none",
                    ),
                    (
                        "organization_graph_version",
                        str(run.organization.graph.version.value) if run.organization else "none",
                    ),
                    ("strategy_version", run.strategy_version),
                    ("policy_version", run.policy.version),
                    ("replan_count", str(run.replan_count)),
                    ("agent_run_count", str(run.agent_run_count)),
                    *metadata,
                ),
            )
        )

    def _plan_event(self, plan: PlanVersion, kind: EventType) -> None:
        self.store.append_event(
            Event(
                self.ids.event_id(),
                plan.workspace_id,
                kind,
                SubjectType.ORCHESTRATION_PLAN,
                str(plan.id),
                plan.version,
                self.clock.now(),
                (("plan_version", str(plan.version.value)),),
            )
        )

    def _delegation_event(
        self,
        delegation: Delegation,
        kind: EventType,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self.store.append_event(
            Event(
                self.ids.event_id(),
                delegation.workspace_id,
                kind,
                SubjectType.DELEGATION,
                str(delegation.id),
                delegation.version,
                self.clock.now(),
                metadata,
            )
        )
