"""Repeatable, offline Stage 11 query measurement; not a production SLO."""

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from statistics import median
from time import perf_counter

from agent_company_os.adapters.clocks import SystemClock
from agent_company_os.adapters.ids import SystemIdGenerator
from agent_company_os.adapters.operator_store import (
    SecureOperatorSecrets,
    SqliteOperatorStore,
    migrate_operator_database,
)
from agent_company_os.adapters.sqlite_database import migrate_database
from agent_company_os.adapters.sqlite_inspection import SqliteInspectionCatalog
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.application.audit import AuditQueryService
from agent_company_os.application.operator import OperatorService
from agent_company_os.application.operator_queries import OperatorQueryService
from agent_company_os.application.recovery import RecoveryService
from agent_company_os.application.service import CreateGoalCommand, CreateTaskCommand, DomainService
from agent_company_os.application.tool_runtime import ToolRuntimeService
from agent_company_os.domain.operator import OperatorId, OperatorRole
from agent_company_os.operator_cli import seed_aurora


def measure(canonical: Path, identity: Path, extra_goals: int = 200) -> dict[str, object]:
    if not 1 <= extra_goals <= 500:
        raise ValueError("extra_goals must be 1..500")
    canonical.parent.mkdir(parents=True, exist_ok=True)
    identity.parent.mkdir(parents=True, exist_ok=True)
    migrate_database(canonical)
    migrate_operator_database(identity)
    workspace = seed_aurora(canonical)
    group, accounts = SqliteStoreGroup(canonical), SqliteOperatorStore(identity)
    try:
        clock, ids = SystemClock(), SystemIdGenerator()
        domain = DomainService(group.domain, clock, ids)
        with group.transaction():
            for index in range(extra_goals):
                goal = domain.create_goal(
                    CreateGoalCommand(workspace, f"Synthetic workload {index:04}", ("Reviewed",))
                )
                goal = domain.activate_goal(goal.id, goal.version)
                for task_index in range(5):
                    domain.create_task(
                        CreateTaskCommand(
                            workspace, goal.id, f"Work item {task_index}", ("Reviewed",)
                        )
                    )
        operators = OperatorService(accounts, group.domain, clock, SecureOperatorSecrets())
        credential = operators.provision_local(workspace, OperatorId("bench"), OperatorRole.AUDITOR)
        token = operators.login(credential.value).value
        tools = ToolRuntimeService(group.runtime, group.registry, clock, ids)
        queries = OperatorQueryService(
            operators,
            group.runtime,
            AuditQueryService(group.runtime),
            RecoveryService(group.runtime, tools, clock, ids, group.orchestration),
            SqliteInspectionCatalog(group),
        )
        first_goal = group.domain.goals(workspace)[0].id
        run_id = group.runtime.runs(workspace)[0].id
        paths: dict[str, Callable[[], object]] = {
            "goal_list": lambda: queries.goals(token, workspace),
            "goal_detail": lambda: queries.inspect(
                token, workspace, "goals", entity_id=str(first_goal)
            ),
            "agent_run_detail": lambda: queries.run(token, workspace, run_id),
            "organization": lambda: queries.inspect(token, workspace, "departments"),
            "recovery_scan": lambda: queries.recovery_cases(token, workspace),
            "goal_timeline": lambda: queries.goal_timeline(token, workspace, first_goal),
        }
        timings: dict[str, dict[str, float]] = {}
        for name, operation in paths.items():
            samples = []
            for _ in range(4):
                before = perf_counter()
                operation()
                samples.append(round((perf_counter() - before) * 1000, 3))
            timings[name] = {"first_ms": samples[0], "warm_median_ms": median(samples[1:])}
        query_plan = group.connection.execute(
            "EXPLAIN QUERY PLAN SELECT id FROM domain_records "
            "WHERE workspace_id=? AND kind='goal' ORDER BY id LIMIT 25",
            (str(workspace),),
        ).fetchall()
        counts = {
            kind: group.connection.execute(
                "SELECT count(*) FROM domain_records WHERE workspace_id=? AND kind=?",
                (str(workspace), kind),
            ).fetchone()[0]
            for kind in ("goal", "task", "task_attempt", "execution")
        }
        counts["events"] = group.connection.execute(
            "SELECT count(*) FROM domain_audit WHERE workspace_id=? AND kind='event'",
            (str(workspace),),
        ).fetchone()[0]
        operators.logout(token)
        return {
            "workspace_id": str(workspace),
            "counts": counts,
            "timings": timings,
            "query_plan": [list(row) for row in query_plan],
            "runs_per_query": 4,
            "assumption": "same local process and SQLite file; first then three warm reads",
        }
    finally:
        accounts.close()
        group.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline operator query fixture and measurement")
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--goals", type=int, default=200)
    args = parser.parse_args()
    print(json.dumps(measure(args.canonical, args.identity, args.goals), indent=2))


if __name__ == "__main__":
    main()
