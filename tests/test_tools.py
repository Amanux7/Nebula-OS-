import asyncio
import json
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path

import pytest

from agent_company_os.adapters.clocks import FakeClock
from agent_company_os.adapters.fake_model import FakeModel
from agent_company_os.adapters.in_memory import InMemoryDomainStore
from agent_company_os.adapters.runtime_store import InMemoryRuntimeStore
from agent_company_os.adapters.tool_executors import (
    CompanyFactLookup,
    FakeToolExecutor,
    SourceFactLookup,
    output_json,
)
from agent_company_os.adapters.tool_registry import ToolRegistry
from agent_company_os.application.research_agent import research_brief_agent, with_read_only_tools
from agent_company_os.application.runtime import AgentRuntimeService
from agent_company_os.application.service import (
    CreateExecutionCommand,
    CreateGoalCommand,
    CreateTaskAttemptCommand,
    CreateTaskCommand,
    DomainService,
)
from agent_company_os.application.tool_runtime import ToolRuntimeService
from agent_company_os.application.tool_serialization import serialize_receipt
from agent_company_os.application.tool_validation import validate_input, validate_output
from agent_company_os.domain.agent import (
    AgentDefinitionId,
    AgentRun,
    Fact,
    RuntimeLimits,
    SuppliedContext,
)
from agent_company_os.domain.decisions import Action, ModelFailure, parse_decision
from agent_company_os.domain.errors import InvariantViolation, VersionConflict, WorkspaceMismatch
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.tools import (
    CompanyLookupInput,
    ExecutorKind,
    RetryPolicy,
    ToolDefinition,
    ToolError,
    ToolFailure,
    ToolGrant,
    ToolId,
    ToolInvocation,
    ToolOutput,
    ToolReceipt,
    ToolRisk,
    ToolVersion,
)
from agent_company_os.ports.tools import ToolExecutor

FACT = Fact("pricing", "$49/month", "approved_001")
CASES = json.loads((Path(__file__).parent / "fixtures/agent_eval/tool_cases.json").read_text())


def decision(kind: str, payload: object) -> str:
    return json.dumps({"schema_version": 1, "action_type": kind, "payload": payload})


def call(tool: str = "company", arguments: object = None) -> str:
    return decision(
        "call_tool",
        {
            "tool_id": tool,
            "arguments": {"company_name": "Acme"} if arguments is None else arguments,
        },
    )


def complete(
    source: str = "tool_receipt:test-tool-receipt-0001:approved_001", value: str = "$49/month"
) -> str:
    return decision(
        "complete_task",
        {"findings": [{"key": "pricing", "value": value, "source_id": source}], "gaps": []},
    )


WAIT = decision("request_more_context", {"missing_fields": ["pricing"]})


@dataclass
class Harness:
    runtime: AgentRuntimeService
    tools: ToolRuntimeService
    registry: ToolRegistry
    store: InMemoryRuntimeStore
    run: AgentRun
    company: ToolVersion
    model: FakeModel

    def drive(self) -> AgentRun:
        self.run = asyncio.run(
            self.runtime.drive(self.run.workspace_id, self.run.id, self.run.version)
        )
        return self.run

    def receipts(self) -> tuple[ToolReceipt, ...]:
        return self.store.tool_receipts(self.run.workspace_id, self.run.id)


def setup(
    service: DomainService,
    clock: FakeClock,
    responses: tuple[str | Exception, ...],
    executor: ToolExecutor | None = None,
    *,
    limits: RuntimeLimits | None = None,
    risk: ToolRisk = ToolRisk.READ_ONLY,
    grants: tuple[ToolGrant, ...] | None = None,
    supplied: bool = False,
) -> Harness:
    workspace = service.create_workspace("Tool research")
    goal = service.create_goal(
        CreateGoalCommand(workspace.id, "Compare approved pricing", ("Grounded",))
    )
    goal = service.activate_goal(goal.id, goal.version)
    task = service.create_task(
        CreateTaskCommand(workspace.id, goal.id, "Research pricing", ("Exact evidence",))
    )
    task = service.ready_task(task.id, task.version)
    task = service.start_task(task.id, task.version)
    execution = service.create_execution(
        CreateExecutionCommand(workspace.id, goal.id, "test-user", 5)
    )
    execution = service.start_execution(execution.id, execution.version)
    attempt = service.create_task_attempt(
        CreateTaskAttemptCommand(workspace.id, task.id, execution.id)
    )
    attempt = service.start_task_attempt(attempt.id, attempt.version)
    registry = ToolRegistry()
    company = ToolVersion(
        ToolDefinition(
            ToolId("company"), workspace.id, "Company Fact Lookup", "Approved fixture facts", risk
        ),
        Version(1),
        ExecutorKind.COMPANY_LOOKUP,
        "company_lookup.v1",
    )
    source = ToolVersion(
        ToolDefinition(
            ToolId("source"), workspace.id, "Source Fact Lookup", "Approved source facts"
        ),
        Version(1),
        ExecutorKind.SOURCE_LOOKUP,
        "source_lookup.v1",
    )
    registry.publish(company, executor or CompanyFactLookup({"Acme": (FACT,)}))
    registry.publish(source, SourceFactLookup((FACT,)))
    assert isinstance(service.store, InMemoryDomainStore)
    store = InMemoryRuntimeStore(service.store)
    definition = research_brief_agent(workspace.id, AgentDefinitionId(str(service.ids.event_id())))
    store.publish(definition)
    upgraded = with_read_only_tools(
        definition, grants if grants is not None else (company.grant, source.grant)
    )
    store.publish(upgraded)
    tools = ToolRuntimeService(store, registry, clock, service.ids)
    model = FakeModel(responses)
    runtime = AgentRuntimeService(store, clock, service.ids, model, tools)
    context = SuppliedContext(workspace.id, task.id, ("pricing",), (FACT,) if supplied else ())
    run = runtime.start(
        workspace.id, upgraded.definition.id, upgraded.version, attempt.id, context, limits
    )
    return Harness(runtime, tools, registry, store, run, company, model)


@pytest.mark.parametrize(
    "case", ["tool_needed", "tool_not_needed", "repeated_request", "two_tools"]
)
def test_deterministic_tool_eval(service: DomainService, clock: FakeClock, case: str) -> None:
    data = CASES[case]
    calls = tuple(
        call(tool, {"source_id": "approved_001", "keys": ["pricing"]})
        if tool == "source"
        else call(tool)
        for tool in data["tools"]
    )
    h = setup(
        service,
        clock,
        (*calls, complete("approved_001") if data["supplied"] else complete()),
        supplied=data["supplied"],
    )
    assert h.drive().status == "succeeded"
    assert len(h.receipts()) == len(calls)
    assert h.run.result is not None
    assert h.store.domain.get_task(h.run.task_id).status == "completed"
    assert h.store.domain.get_goal(h.run.goal_id).status == "active"
    if calls:
        receipt = h.receipts()[0]
        assert receipt.invocation.tool_version == h.company
        assert receipt.invocation.validated_input == CompanyLookupInput("Acme")
        assert receipt.output == ToolOutput("Acme", (FACT,))
        assert h.model.requests[1].observations[-1].tool_result is not None
        assert not h.model.requests[0].observations


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"company_name": 3},
        {"company_name": ""},
        {"company_name": "Acme", "exec": "bad"},
        {"company_name": "x" * 3000},
    ],
)
def test_invalid_arguments_never_execute(
    service: DomainService, clock: FakeClock, args: object
) -> None:
    fake = FakeToolExecutor(())
    h = setup(service, clock, (call(arguments=args), WAIT), fake)
    assert h.drive().status == "waiting"
    assert not fake.requests and not h.receipts()
    assert h.model.requests[1].observations[-1].message == "validation_error"


@pytest.mark.parametrize(
    "mode",
    [
        "unknown",
        "ungranted",
        "disabled",
        "unpublished",
        "cross_workspace",
        "internal_write",
        "external_write",
        "high_risk",
    ],
)
def test_authorization_before_io(service: DomainService, clock: FakeClock, mode: str) -> None:
    fake = FakeToolExecutor(())
    grants = (
        (ToolGrant(ToolId("company"), Version(2)),)
        if mode == "unpublished"
        else (() if mode == "ungranted" else None)
    )
    risk = ToolRisk(mode) if mode.endswith("write") or mode == "high_risk" else ToolRisk.READ_ONLY
    h = setup(
        service,
        clock,
        (call("unknown" if mode == "unknown" else "company"), WAIT),
        fake,
        grants=grants,
        risk=risk,
    )
    if mode == "disabled":
        h.registry.set_enabled(h.run.workspace_id, ToolId("company"), False)
    if mode == "cross_workspace":
        other = replace(
            h.company, definition=replace(h.company.definition, workspace_id=WorkspaceId("foreign"))
        )
        registry = ToolRegistry()
        registry.publish(other, fake)
        h.tools.registry = registry
    assert h.drive().status == "waiting"
    assert not fake.requests and not h.receipts()
    assert h.model.requests[1].observations[-1].message in ("not_found", "unauthorized")


@pytest.mark.parametrize(
    "result,code",
    [
        ("not json", "malformed_output"),
        ("{}", "malformed_output"),
        ("x" * 9000, "output_too_large"),
        (TimeoutError(), "timeout"),
        (RuntimeError("secret-token"), "internal_executor_error"),
        (ToolFailure(ToolError.RATE_LIMITED), "rate_limited"),
        (ToolFailure(ToolError.UPSTREAM_UNAVAILABLE), "upstream_unavailable"),
        (ToolFailure(ToolError.NOT_FOUND), "not_found"),
        (ToolFailure(ToolError.VALIDATION_ERROR), "validation_error"),
    ],
)
def test_recoverable_failures(
    service: DomainService, clock: FakeClock, result: str | Exception, code: str
) -> None:
    fake = FakeToolExecutor((result,))
    h = setup(service, clock, (call(), WAIT), fake)
    assert h.drive().status == "waiting"
    receipt = h.receipts()[0]
    assert receipt.invocation.error_code == code
    assert receipt.output is None and receipt.remote_outcome == "unknown"
    assert h.model.requests[1].observations[-1].message == code
    assert len(fake.requests) == 1
    assert h.store.domain.get_task(h.run.task_id).status == "in_progress"


@pytest.mark.parametrize("total,per_tool", [(1, 3), (5, 1)])
def test_tool_budget(service: DomainService, clock: FakeClock, total: int, per_tool: int) -> None:
    h = setup(
        service,
        clock,
        (call(), call()),
        limits=RuntimeLimits(max_tool_calls=total, max_calls_per_tool=per_tool),
    )
    assert h.drive().error_code == "tool_budget_exceeded"
    assert len(h.receipts()) == 1


def test_terminal_invocation_replay(service: DomainService, clock: FakeClock) -> None:
    fake = FakeToolExecutor((output_json(ToolOutput("Acme", (FACT,))),))
    h = setup(service, clock, (call(), complete()), fake)
    h.drive()
    action = h.store.actions(h.run.workspace_id)[0]
    events = h.store.events(h.run.workspace_id)
    assert asyncio.run(h.tools.invoke(h.run.workspace_id, h.run.id, action, Version(1))) == h.run
    assert len(fake.requests) == 1 and len(h.receipts()) == 1
    assert h.store.events(h.run.workspace_id) == events
    with pytest.raises(InvariantViolation):
        h.store.finish_tool_invocation(h.receipts()[0])


@pytest.mark.parametrize(
    "mutation",
    [
        "cancel_run",
        "cancel_execution",
        "parent_version",
        "run_version",
        "disable",
        "cancel_coroutine",
        "duplicate",
    ],
)
def test_inflight_races(service: DomainService, clock: FakeClock, mutation: str) -> None:
    async def scenario() -> None:
        entered, gate = asyncio.Event(), asyncio.Event()
        fake = FakeToolExecutor(
            (output_json(ToolOutput("Acme", (FACT,))),), entered=entered, gate=gate
        )
        h = setup(service, clock, (call(), complete()), fake)
        job = asyncio.create_task(h.runtime.drive(h.run.workspace_id, h.run.id, h.run.version))
        await asyncio.wait_for(entered.wait(), 2)
        current = h.store.get_run(h.run.workspace_id, h.run.id)
        assert len(h.store.tool_invocations(current.workspace_id, current.id)) == 1
        if mutation == "cancel_run":
            terminal = h.runtime.cancel(current.workspace_id, current.id, current.version)
        elif mutation == "cancel_execution":
            execution = h.store.domain.get_execution(current.execution_id)
            service.cancel_execution(execution.id, execution.version)
        elif mutation == "parent_version":
            execution = h.store.domain.get_execution(current.execution_id)
            service.wait_execution(execution.id, execution.version)
            execution = h.store.domain.get_execution(current.execution_id)
            service.resume_execution(execution.id, execution.version)
        elif mutation == "run_version":
            h.store.save_run(current.evolve(at=clock.now()), current.version, None)
        elif mutation == "disable":
            h.registry.set_enabled(current.workspace_id, ToolId("company"), False)
        elif mutation == "duplicate":
            action = h.store.actions(current.workspace_id)[0]
            with pytest.raises(InvariantViolation, match="tool_invocation_in_progress"):
                await h.tools.invoke(current.workspace_id, current.id, action, current.version)
        else:
            job.cancel()
        gate.set()
        if mutation == "cancel_coroutine":
            with pytest.raises(asyncio.CancelledError):
                await job
            result = h.store.get_run(current.workspace_id, current.id)
        else:
            result = await job
        if mutation == "duplicate":
            assert result.status == "succeeded"
        else:
            assert result.status in ("failed", "cancelled")
            assert h.receipts()[0].output is None
            assert h.store.domain.get_task(current.task_id).status != "completed"
        if mutation == "cancel_run":
            assert result == terminal
        assert len(fake.requests) == 1

    asyncio.run(scenario())


def test_real_timeout(service: DomainService, clock: FakeClock) -> None:
    async def scenario() -> None:
        fake = FakeToolExecutor((), gate=asyncio.Event())
        h = setup(service, clock, (call(), WAIT), fake)
        registry = ToolRegistry()
        registry.publish(replace(h.company, timeout_seconds=1), fake)
        h.tools.registry = registry
        result = await asyncio.wait_for(
            h.runtime.drive(h.run.workspace_id, h.run.id, h.run.version), 3
        )
        assert result.status == "waiting"
        assert h.receipts()[0].invocation.error_code == ToolError.TIMEOUT

    asyncio.run(scenario())


def test_deadline_during_tool(service: DomainService, clock: FakeClock) -> None:
    fake = FakeToolExecutor(
        (output_json(ToolOutput("Acme", (FACT,))),),
        on_execute=lambda _: clock.advance(timedelta(seconds=61)),
    )
    h = setup(service, clock, (call(), complete()), fake)
    assert h.drive().error_code == "deadline_exceeded"
    assert h.receipts()[0].invocation.error_code == ToolError.TIMEOUT


def test_injection_is_data(service: DomainService, clock: FakeClock) -> None:
    fake = FakeToolExecutor(
        (output_json(ToolOutput("Acme", (FACT,), CASES["injection"]["notes"])),)
    )
    h = setup(service, clock, (call(), call("admin_delete_database"), complete()), fake)
    original = h.run.definition_version
    assert h.drive().status == "succeeded"
    assert h.run.definition_version == original
    assert h.model.requests[2].observations[-1].message == "not_found"
    assert h.model.requests[1].observations[-1].trust == "untrusted_tool_data"
    assert len(fake.requests) == 1


@pytest.mark.parametrize(
    "source,value",
    [
        ("tool_receipt:fake:approved_001", "$49/month"),
        ("tool_receipt:test-tool-receipt-0001:approved_001", "$99/month"),
        ("approved_001", "$49/month"),
    ],
)
def test_fabricated_evidence(
    service: DomainService, clock: FakeClock, source: str, value: str
) -> None:
    h = setup(service, clock, (call(), complete(source, value)))
    assert h.drive().error_code == "ungrounded_fact"


def test_foreign_receipt_and_reserved_source(service: DomainService, clock: FakeClock) -> None:
    first = setup(service, clock, (call(), complete()))
    first.drive()
    second = setup(service, clock, (complete(),), supplied=True)
    assert second.drive().error_code == "ungrounded_fact"
    with pytest.raises(WorkspaceMismatch):
        first.store.tool_receipts(second.run.workspace_id, first.run.id)
    with pytest.raises(InvariantViolation):
        replace(first.run.context, facts=(Fact("pricing", "$49/month", "tool_receipt:fake"),))


def test_history_and_context_bounds(service: DomainService, clock: FakeClock) -> None:
    h = setup(
        service, clock, (call(), call(), complete()), limits=RuntimeLimits(recent_observations=1)
    )
    assert h.drive().status == "succeeded"
    old = h.receipts()[0]
    h.registry.publish(
        replace(h.company, version=Version(2)),
        CompanyFactLookup({"Acme": (replace(FACT, value="changed"),)}),
    )
    assert h.receipts()[0] == old
    assert old.output is not None and old.output.facts == (FACT,)
    assert all(len(request.observations) <= 1 for request in h.model.requests)
    with pytest.raises(InvariantViolation):
        h.registry.publish(h.company, CompanyFactLookup({}))
    with pytest.raises(InvariantViolation):
        replace(h.run.definition_version, allowed_tools=(h.company.grant, h.company.grant))


def test_atomic_result_rollback(
    service: DomainService, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeToolExecutor((output_json(ToolOutput("Acme", (FACT,))),))
    h = setup(service, clock, (call(), complete()), fake)
    original = h.store.finish_tool_invocation
    count = 0

    def fail_once(receipt: ToolReceipt) -> None:
        nonlocal count
        count += 1
        original(receipt)
        if count == 1:
            raise RuntimeError("simulated_commit_fault")

    monkeypatch.setattr(h.store, "finish_tool_invocation", fail_once)
    assert h.drive().status == "failed"
    assert len(h.receipts()) == 1 and h.receipts()[0].output is None
    assert h.receipts()[0].invocation.error_code == ToolError.INTERNAL_EXECUTOR_ERROR
    assert not h.tools.evidence(h.run)
    assert len(fake.requests) == 1
    assert not any(
        obs.message == "tool_succeeded" for obs in h.store.observations(h.run.workspace_id)
    )


@pytest.mark.parametrize(
    "raw",
    [
        '{"company_name":"Acme","company_name":"Other"}',
        '{"company_name":true}',
        '{"company_name":"\\ud800"}',
    ],
)
def test_input_edge_cases(service: DomainService, clock: FakeClock, raw: str) -> None:
    h = setup(service, clock, ())
    with pytest.raises(ToolFailure):
        validate_input(raw, h.company)


@pytest.mark.parametrize(
    "change", ["schema", "subject", "extra", "duplicate", "spoofed_source", "size", "notes"]
)
def test_output_contract(service: DomainService, clock: FakeClock, change: str) -> None:
    h = setup(service, clock, ())
    data = json.loads(output_json(ToolOutput("Acme", (FACT,))))
    if change == "schema":
        data["schema_version"] = True
    if change == "subject":
        data["subject"] = "Other"
    if change == "extra":
        data["secret"] = "no"
    if change == "duplicate":
        data["facts"] *= 2
    if change == "spoofed_source":
        data["facts"][0]["source_id"] = "tool_receipt:fake"
    if change == "size":
        data["facts"][0]["value"] = "x" * 513
    if change == "notes":
        data["notes"] = "x" * 513
    with pytest.raises(ToolFailure):
        validate_output(json.dumps(data), h.company, CompanyLookupInput("Acme"))


def test_retry_policy() -> None:
    assert not RetryPolicy().should_retry(ToolError.TIMEOUT)
    with pytest.raises(InvariantViolation):
        RetryPolicy(1)


@pytest.mark.parametrize(
    "case",
    ["unauthorized_tool", "wrong_tool_selection", "tool_failure_recovery", "fabricated_receipt"],
)
def test_adversarial_eval_cases(service: DomainService, clock: FakeClock, case: str) -> None:
    data = CASES[case]
    fake = FakeToolExecutor((ToolFailure(ToolError.UPSTREAM_UNAVAILABLE),))
    if case == "fabricated_receipt":
        h = setup(service, clock, (complete(data["source"]),), supplied=True)
        assert h.drive().error_code == data["expected_error"]
    elif case == "tool_failure_recovery":
        h = setup(service, clock, (call(), WAIT), fake)
        assert h.drive().status == data["expected_status"]
    else:
        h = setup(
            service,
            clock,
            (call(data["tool_id"], data["arguments"]), WAIT),
            fake,
            grants=(ToolGrant(ToolId("company"), Version(1)),)
            if case == "unauthorized_tool"
            else None,
        )
        assert h.drive().status == "waiting"
        assert h.model.requests[1].observations[-1].message == data["error"]
        assert not fake.requests


def test_same_workspace_other_run_receipt(service: DomainService, clock: FakeClock) -> None:
    h = setup(service, clock, (call(), complete()))
    h.drive()
    goal = h.store.domain.get_goal(h.run.goal_id)
    task = service.create_task(
        CreateTaskCommand(h.run.workspace_id, goal.id, "Other task", ("Grounded",))
    )
    task = service.ready_task(task.id, task.version)
    task = service.start_task(task.id, task.version)
    execution = service.create_execution(
        CreateExecutionCommand(h.run.workspace_id, goal.id, "caller", 5)
    )
    execution = service.start_execution(execution.id, execution.version)
    attempt = service.create_task_attempt(
        CreateTaskAttemptCommand(h.run.workspace_id, task.id, execution.id)
    )
    attempt = service.start_task_attempt(attempt.id, attempt.version)
    h.runtime.model = FakeModel((complete(),))
    other = h.runtime.start(
        h.run.workspace_id,
        h.run.definition_version.definition.id,
        Version(2),
        attempt.id,
        SuppliedContext(h.run.workspace_id, task.id, ("pricing",), (FACT,)),
    )
    assert not h.tools.evidence(other)
    result = asyncio.run(h.runtime.drive(other.workspace_id, other.id, other.version))
    assert result.error_code == "ungrounded_fact"


def test_receipt_export_and_audit(service: DomainService, clock: FakeClock) -> None:
    h = setup(service, clock, (call(), complete()))
    h.drive()
    receipt = h.receipts()[0]
    exported = json.loads(json.dumps(serialize_receipt(receipt)))
    assert exported["tool_version"] == 1
    assert exported["validated_input"] == {"company_name": "Acme"}
    assert exported["output"]["facts"][0]["value"] == FACT.value
    assert exported["started_at"].endswith("+00:00")
    assert exported["status"] == "succeeded" and exported["schema_version"] == 1
    assert h.run.policy_version == "read-only-tools-v1"
    events = [
        e
        for e in h.store.events(h.run.workspace_id)
        if e.event_type.value == "tool_receipt_recorded"
    ]
    metadata = dict(events[0].metadata)
    assert metadata["tool_version"] == "1" and metadata["retry_count"] == "0"
    assert metadata["tool_receipt_id"] == str(receipt.id)
    assert not any(FACT.value in value for _, value in events[0].metadata)


def test_atomic_claim_rollback(
    service: DomainService, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeToolExecutor(())
    h = setup(service, clock, (call(),), fake)
    original = h.store.add_tool_invocation

    def fail_after_claim(invocation: ToolInvocation) -> None:
        original(invocation)
        raise RuntimeError("claim_commit_failure")

    monkeypatch.setattr(h.store, "add_tool_invocation", fail_after_claim)
    assert h.drive().status == "failed"
    assert not fake.requests and not h.receipts()
    assert not h.store.tool_invocations(h.run.workspace_id, h.run.id)


def test_bounded_preview_and_overflow(service: DomainService, clock: FakeClock) -> None:
    facts = (FACT, *(Fact(f"irrelevant{i}", "x" * 100, "approved_001") for i in range(9)))
    fake = FakeToolExecutor((output_json(ToolOutput("Acme", facts)),))
    h = setup(service, clock, (call(), complete()), fake)
    assert h.drive().status == "succeeded"
    output = h.receipts()[0].output
    assert output is not None and len(output.facts) == 10
    data = h.model.requests[1].observations[-1].tool_result
    assert data is not None and len(data.facts) == 5
    from agent_company_os.application.context import ContextAssembler

    preview_run = replace(
        h.run,
        limits=replace(h.run.limits, max_context_chars=1000),
        working_state=replace(h.run.working_state, observations=h.model.requests[1].observations),
    )
    with pytest.raises(ModelFailure, match="context_overflow"):
        ContextAssembler().assemble(
            preview_run,
            h.store.domain.get_goal(h.run.goal_id),
            h.store.domain.get_task(h.run.task_id),
            (h.company,),
        )


def test_source_contract_and_utf8_limits(service: DomainService, clock: FakeClock) -> None:
    h = setup(service, clock, ())
    version = h.registry.resolve(
        h.run.workspace_id, ToolGrant(ToolId("source"), Version(1))
    ).version
    for arguments in (
        {"source_id": "approved_001", "keys": []},
        {"source_id": "approved_001", "keys": ["a", "a"]},
    ):
        with pytest.raises(ToolFailure):
            validate_input(json.dumps(arguments), version)
    request = validate_input('{"source_id":"approved_001","keys":["pricing"]}', version)
    with pytest.raises(ToolFailure):
        validate_output(
            output_json(ToolOutput("approved_001", (replace(FACT, source_id="foreign"),))),
            version,
            request,
        )
    with pytest.raises(ToolFailure):
        validate_input(
            json.dumps({"company_name": "é" * 120}, ensure_ascii=False),
            replace(h.company, max_input_bytes=200),
        )
    with pytest.raises(ToolFailure):
        validate_output(
            output_json(ToolOutput("Acme", (FACT,), "é" * 300)),
            replace(h.company, max_output_bytes=600),
            CompanyLookupInput("Acme"),
        )


def test_call_schema_rejects_extra_authority() -> None:
    with pytest.raises(ModelFailure):
        parse_decision(
            decision(
                "call_tool", {"tool_id": "company", "arguments": {}, "allowed_tools": ["admin"]}
            ),
            8000,
        )


def test_stale_preflight_and_tampered_replay(service: DomainService, clock: FakeClock) -> None:
    async def scenario() -> None:
        h = setup(service, clock, ())
        current = h.run.evolve(
            at=clock.now(),
            working_state=replace(h.run.working_state, iteration=1, invocation_pending=True),
        )
        h.store.save_run(current, h.run.version, None)
        action = Action(
            service.ids.action_id(),
            current.id,
            current.workspace_id,
            parse_decision(call(), 8000),
            1,
        )
        h.store.append_action(action)
        with pytest.raises(VersionConflict):
            await h.tools.invoke(current.workspace_id, current.id, action, Version(1))
        assert not h.receipts()
        await h.tools.invoke(current.workspace_id, current.id, action, current.version)
        tampered = replace(
            action, decision=parse_decision(call(arguments={"company_name": "Other"}), 8000)
        )
        with pytest.raises(InvariantViolation):
            await h.tools.invoke(current.workspace_id, current.id, tampered, current.version)
        assert len(h.receipts()) == 1

    asyncio.run(scenario())


def test_continuing_storage_failure_never_reexecutes(
    service: DomainService, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeToolExecutor((output_json(ToolOutput("Acme", (FACT,))),))
    h = setup(service, clock, (call(), complete()), fake)

    def unavailable(receipt: ToolReceipt) -> None:
        raise RuntimeError("unavailable")

    monkeypatch.setattr(h.store, "finish_tool_invocation", unavailable)
    assert h.drive().status == "failed"
    assert not h.receipts() and not h.tools.evidence(h.run)
    assert len(fake.requests) == 1
    invocation = h.store.tool_invocations(h.run.workspace_id, h.run.id)[0]
    assert invocation.status == "running"  # Reconciliation is unavailable, not falsely succeeded.
    action = h.store.actions(h.run.workspace_id)[0]
    with pytest.raises(InvariantViolation):
        asyncio.run(h.tools.invoke(h.run.workspace_id, h.run.id, action, h.run.version))
    assert len(fake.requests) == 1
