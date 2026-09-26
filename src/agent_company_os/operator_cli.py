"""Explicit local host commands. No task is automatically dispatched at startup."""

import argparse
import asyncio
import getpass
import json
from dataclasses import replace
from pathlib import Path

from agent_company_os.adapters.clocks import SystemClock
from agent_company_os.adapters.fake_model import FakeModel
from agent_company_os.adapters.ids import SystemIdGenerator
from agent_company_os.adapters.knowledge_ingestion import TextKnowledgeIngestor
from agent_company_os.adapters.lexical_memory import LexicalMemoryRetriever
from agent_company_os.adapters.lexical_retrieval import LexicalKnowledgeRetriever
from agent_company_os.adapters.operator_store import (
    SecureOperatorSecrets,
    SqliteOperatorStore,
    migrate_operator_database,
)
from agent_company_os.adapters.recoverable_fixture import (
    RecoverableFixtureExecutor,
    bootstrap_fixture,
)
from agent_company_os.adapters.sqlite_backup import SqliteBackupAdapter
from agent_company_os.adapters.sqlite_database import migrate_database
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.application.backup import BackupService
from agent_company_os.application.governance import GovernanceService
from agent_company_os.application.knowledge import KnowledgeService, PublishKnowledgeSource
from agent_company_os.application.memory import MemoryService, ProposeMemoryCandidate
from agent_company_os.application.operator import OperatorService
from agent_company_os.application.organization import OrganizationService
from agent_company_os.application.research_agent import research_brief_agent
from agent_company_os.application.runtime import AgentRuntimeService
from agent_company_os.application.service import (
    CreateExecutionCommand,
    CreateGoalCommand,
    CreateTaskAttemptCommand,
    CreateTaskCommand,
    DomainService,
)
from agent_company_os.application.tool_runtime import ToolRuntimeService
from agent_company_os.domain.agent import (
    ActionType,
    AgentDefinition,
    AgentDefinitionId,
    Fact,
    SuppliedContext,
)
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.governance import (
    ApprovalPolicy,
    DecisionKind,
    ReviewerId,
    ReviewerPrincipal,
)
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.knowledge import SourceType, TrustClass
from agent_company_os.domain.memory import (
    MemoryAuthority,
    MemoryProvenance,
    MemoryProvenanceKind,
    MemoryScope,
    MemoryScopeKind,
    MemoryType,
)
from agent_company_os.domain.operator import OperatorId, OperatorRole
from agent_company_os.domain.organization import (
    CapabilityDefinition,
    Department,
    DepartmentMembership,
    OrganizationGraphVersion,
    OrgRole,
    RegisteredAgent,
)
from agent_company_os.domain.tools import (
    ExecutorKind,
    ToolDefinition,
    ToolId,
    ToolRisk,
    ToolVersion,
)
from agent_company_os.operator_host import HostConfig, create_server


def seed_aurora(path: Path) -> WorkspaceId:
    """Create clearly synthetic records using the same application commands as tests."""
    group = SqliteStoreGroup(path)
    try:
        if group.domain.workspaces():
            raise InvariantViolation("seed_requires_empty_canonical_database")
        clock, ids = SystemClock(), SystemIdGenerator()
        domain = DomainService(group.domain, clock, ids)
        workspace = domain.create_workspace("Aurora Desk · synthetic demo")
        ws = workspace.id
        knowledge = KnowledgeService(
            group.knowledge, TextKnowledgeIngestor(), LexicalKnowledgeRetriever(), clock, ids
        )
        knowledge.publish_source(
            PublishKnowledgeSource(
                ws,
                "Approved competitor brief notes",
                SourceType.TEXT,
                TrustClass.APPROVED_INTERNAL,
                b"Aurora Desk is a synthetic Stage 11 inspection fixture. "
                b"No customer data or real integration is present.",
            )
        )
        fixture_path = path.with_name(path.stem + "-remote.sqlite")
        bootstrap_fixture(fixture_path)
        fixture_executor = RecoverableFixtureExecutor(fixture_path)
        tool = ToolVersion(
            ToolDefinition(
                ToolId(str(ids.event_id())),
                ws,
                "Fixture delivery",
                "Offline deterministic message",
                ToolRisk.EXTERNAL_WRITE,
            ),
            Version(1),
            ExecutorKind.SEND_FIXTURE_MESSAGE,
            "send_fixture_message.v1",
        )
        group.registry.publish(tool, fixture_executor)
        names = ("Research", "Product", "Marketing")
        capabilities = tuple(
            CapabilityDefinition(ids.capability_id(), ws, name.lower()) for name in names
        )
        departments = tuple(Department(ids.department_id(), ws, name) for name in names)
        roles = tuple(OrgRole(ids.org_role_id(), ws, name.lower()) for name in names)
        definitions = []
        for index, name in enumerate(names):
            definition = research_brief_agent(ws, AgentDefinitionId(str(ids.event_id())))
            definition = replace(
                definition,
                definition=AgentDefinition(definition.definition.id, ws, f"{name} Specialist"),
                role=name.lower(),
                capabilities=(name.lower(),),
                capability_ids=(capabilities[index].id,),
            )
            if name == "Marketing":
                definition = replace(
                    definition,
                    allowed_actions=tuple(ActionType),
                    allowed_tools=(tool.grant,),
                    autonomy_ceiling=2,
                )
            group.runtime.publish(definition)
            definitions.append(definition)
        reviewer = ReviewerPrincipal(ReviewerId("synthetic-reviewer"), ws)
        group.runtime.publish_approval_policy(
            ApprovalPolicy(ws, Version(1), (tool.grant,), ("customer:paper-kite",), (reviewer,))
        )
        org = OrganizationService(group.organization, clock, ids)
        graph = org.create(ws, "Aurora Desk organization")
        version = OrganizationGraphVersion(
            graph.id,
            ws,
            Version(1),
            clock.now(),
            departments,
            roles,
            capabilities,
            tuple(RegisteredAgent(ws, d.definition.id, d.version) for d in definitions),
            tuple(
                DepartmentMembership(ws, d.definition.id, departments[i].id, roles[i].id)
                for i, d in enumerate(definitions)
            ),
        )
        org.publish(version, graph.revision)
        current = group.organization.graph(ws)
        org.activate(ws, Version(1), current.revision)

        complete = domain.create_goal(
            CreateGoalCommand(ws, "Produce a competitor launch brief", ("Three reviewed sections",))
        )
        complete = domain.activate_goal(complete.id, complete.version)
        execution = domain.create_execution(CreateExecutionCommand(ws, complete.id, "fixture", 5))
        execution = domain.start_execution(execution.id, execution.version)
        tasks = tuple(
            domain.create_task(CreateTaskCommand(ws, complete.id, title, ("Reviewed",)))
            for title in ("Research alternatives", "Analyze product fit", "Draft positioning")
        )
        source_run = None
        for index, task in enumerate(tasks):
            task = domain.ready_task(task.id, task.version)
            task = domain.start_task(task.id, task.version)
            attempt = domain.create_task_attempt(
                CreateTaskAttemptCommand(ws, task.id, execution.id)
            )
            attempt = domain.start_task_attempt(attempt.id, attempt.version)
            if index == 0:
                fact = Fact("pricing", "Synthetic $49", "fixture-statement")
                completion = json.dumps(
                    {
                        "schema_version": 1,
                        "action_type": "complete_task",
                        "payload": {
                            "findings": [
                                {"key": fact.key, "value": fact.value, "source_id": fact.source_id}
                            ],
                            "gaps": [],
                        },
                    }
                )
                runtime = AgentRuntimeService(group.runtime, clock, ids, FakeModel((completion,)))
                source_run = runtime.start(
                    ws,
                    definitions[0].definition.id,
                    Version(1),
                    attempt.id,
                    SuppliedContext(ws, task.id, ("pricing",), (fact,)),
                )
                source_run = asyncio.run(runtime.drive(ws, source_run.id, source_run.version))
            else:
                attempt = domain.succeed_task_attempt(attempt.id, attempt.version)
                domain.complete_task(task.id, attempt.id, task.version)
        domain.succeed_execution(execution.id, execution.version)
        domain.satisfy_goal(complete.id, complete.version)
        if source_run is None:
            raise InvariantViolation("fixture_source_run_missing")
        memory = MemoryService(group.memory, LexicalMemoryRetriever(), clock, ids)
        candidate = memory.propose(
            ProposeMemoryCandidate(
                ws,
                source_run.id,
                MemoryType.EPISODIC,
                "Aurora demo customer",
                "Synthetic $49",
                MemoryScope(MemoryScopeKind.CUSTOMER, "paper-kite"),
                MemoryProvenance(
                    MemoryProvenanceKind.USER_STATEMENT,
                    source_run.id,
                    ("fixture-statement",),
                    MemoryAuthority.STATED,
                ),
                claim_key="pricing",
                claim_value="Synthetic $49",
            )
        )
        memory.approve(ws, candidate.id, candidate.version, "synthetic-reviewer")

        active = domain.create_goal(
            CreateGoalCommand(ws, "Deliver a customer competitor brief", ("Human review",))
        )
        active = domain.activate_goal(active.id, active.version)
        task = domain.create_task(
            CreateTaskCommand(ws, active.id, "Prepare delivery summary", ("Exact evidence",))
        )
        task = domain.ready_task(task.id, task.version)
        task = domain.start_task(task.id, task.version)
        execution = domain.create_execution(CreateExecutionCommand(ws, active.id, "fixture", 3))
        execution = domain.start_execution(execution.id, execution.version)
        attempt = domain.create_task_attempt(CreateTaskAttemptCommand(ws, task.id, execution.id))
        attempt = domain.start_task_attempt(attempt.id, attempt.version)
        AgentRuntimeService(group.runtime, clock, ids, FakeModel(())).start(
            ws,
            definitions[0].definition.id,
            Version(1),
            attempt.id,
            SuppliedContext(ws, task.id, ("synthetic",), ()),
            organization_version=Version(1),
        )
        governance = GovernanceService(group.runtime, clock, ids)
        tools = ToolRuntimeService(group.runtime, group.registry, clock, ids, governance)
        proposal = json.dumps(
            {
                "schema_version": 1,
                "action_type": "call_tool",
                "payload": {
                    "tool_id": str(tool.definition.id),
                    "arguments": {
                        "destination": "customer:paper-kite",
                        "message": "Synthetic Aurora Desk competitor brief is ready.",
                    },
                },
            }
        )
        for approved in (False, True):
            goal = domain.create_goal(
                CreateGoalCommand(
                    ws,
                    "Review synthetic delivery" if not approved else "Deliver synthetic brief",
                    ("Exact human review",),
                )
            )
            goal = domain.activate_goal(goal.id, goal.version)
            delivery = domain.create_task(
                CreateTaskCommand(ws, goal.id, "Send fixture message", ("Observed receipt",))
            )
            delivery = domain.ready_task(delivery.id, delivery.version)
            delivery = domain.start_task(delivery.id, delivery.version)
            execution = domain.create_execution(CreateExecutionCommand(ws, goal.id, "fixture", 2))
            execution = domain.start_execution(execution.id, execution.version)
            attempt = domain.create_task_attempt(
                CreateTaskAttemptCommand(ws, delivery.id, execution.id)
            )
            attempt = domain.start_task_attempt(attempt.id, attempt.version)
            runtime = AgentRuntimeService(group.runtime, clock, ids, FakeModel((proposal,)), tools)
            run = runtime.start(
                ws,
                definitions[2].definition.id,
                Version(1),
                attempt.id,
                SuppliedContext(ws, delivery.id, ("synthetic",), ()),
            )
            run = asyncio.run(runtime.drive(ws, run.id, run.version))
            if approved:
                intent = group.runtime.governed_actions(ws)[-1]
                governance.decide(
                    ws, intent.intent.id, intent.intent.fingerprint, reviewer, DecisionKind.APPROVED
                )
                asyncio.run(runtime.resume_approval(ws, run.id, intent.intent.id, run.version))
        fixture_executor.close()
        return ws
    finally:
        group.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Company OS local operator host")
    parser.add_argument(
        "command", choices=("bootstrap", "seed-aurora", "provision", "backup", "restore", "serve")
    )
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--workspace", help="Workspace ID for trusted provisioning")
    parser.add_argument("--operator", help="Operator ID for trusted provisioning")
    parser.add_argument("--role", choices=[role.value for role in OperatorRole], default="admin")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--backups", type=Path, default=Path(".local/backups"))
    parser.add_argument("--restores", type=Path, default=Path(".local/restores"))
    parser.add_argument("--name", help="Single-component backup name")
    parser.add_argument("--destination", help="New single-component restore name")
    args = parser.parse_args()
    if args.command == "bootstrap":
        args.canonical.parent.mkdir(parents=True, exist_ok=True)
        args.identity.parent.mkdir(parents=True, exist_ok=True)
        migrate_database(args.canonical)
        migrate_operator_database(args.identity)
        print("Databases migrated. No operator has been provisioned.")
    elif args.command == "seed-aurora":
        print("Synthetic workspace:", seed_aurora(args.canonical))
    elif args.command == "provision":
        if not args.workspace or not args.operator:
            parser.error("--workspace and --operator are required for provision")
        group, identity = SqliteStoreGroup(args.canonical), SqliteOperatorStore(args.identity)
        try:
            service = OperatorService(
                identity, group.domain, SystemClock(), SecureOperatorSecrets()
            )
            credential = service.provision_local(
                WorkspaceId(args.workspace), OperatorId(args.operator), OperatorRole(args.role)
            )
            # This command is an explicit trusted local one-time credential delivery.
            print("One-time credential:", credential.value)
        finally:
            identity.close()
            group.close()
    elif args.command in ("backup", "restore"):
        if (
            not args.workspace
            or not args.name
            or (args.command == "restore" and not args.destination)
        ):
            parser.error("--workspace, --name and (for restore) --destination are required")
        group, identity = SqliteStoreGroup(args.canonical), SqliteOperatorStore(args.identity)
        try:
            operators = OperatorService(
                identity, group.domain, SystemClock(), SecureOperatorSecrets()
            )
            # Read secret only from the local terminal, not argv, environment, or HTTP.
            supplied_credential = getpass.getpass("Operator credential: ")
            session = operators.login(supplied_credential).value
            backups = BackupService(
                operators, SqliteBackupAdapter(args.canonical, args.backups, args.restores)
            )
            workspace = WorkspaceId(args.workspace)
            if args.command == "backup":
                result = backups.create(session, workspace, args.name)
                print("Backup created:", result.backup_id, result.sha256)
            else:
                result = backups.restore(session, workspace, args.name, args.destination)
                print(
                    "Restored in quarantine:", args.restores / args.destination / "canonical.sqlite"
                )
                print("Source backup:", result.backup_id)
            operators.logout(session)
        finally:
            identity.close()
            group.close()
    else:
        server = create_server(HostConfig(args.canonical, args.identity, args.port))
        print(f"Operator console: http://127.0.0.1:{server.server_port}/")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
