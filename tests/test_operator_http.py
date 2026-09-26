"""Real loopback requests against the canonical SQLite-backed host."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from http.client import HTTPConnection
from pathlib import Path
from threading import Event as ThreadEvent
from threading import Thread
from time import sleep

import pytest

from agent_company_os.adapters.clocks import FakeClock
from agent_company_os.adapters.ids import DeterministicIdGenerator
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
from agent_company_os.application.service import CreateGoalCommand, DomainService
from agent_company_os.application.tool_runtime import ToolRuntimeService
from agent_company_os.domain.operator import OperatorId, OperatorRole
from agent_company_os.operator_cli import seed_aurora
from agent_company_os.operator_host import HostConfig, create_server


@pytest.fixture
def site(tmp_path: Path) -> Iterator[tuple[int, str, str, str, str]]:
    canonical, identity = tmp_path / "canonical.sqlite", tmp_path / "identity.sqlite"
    migrate_database(canonical)
    migrate_operator_database(identity)
    group, accounts = SqliteStoreGroup(canonical), SqliteOperatorStore(identity)
    try:
        clock = FakeClock(datetime(2026, 9, 26, tzinfo=UTC))
        domain = DomainService(group.domain, clock, DeterministicIdGenerator("http"))
        workspace = domain.create_workspace("Aurora Desk")
        foreign = domain.create_workspace("Other workspace")
        goal = domain.create_goal(
            CreateGoalCommand(workspace.id, "<script>alert('x')</script>", ("evidence",))
        )
        foreign_goal = domain.create_goal(
            CreateGoalCommand(foreign.id, "secret foreign goal", ("evidence",))
        )
        operators = OperatorService(accounts, group.domain, clock, SecureOperatorSecrets())
        admin = operators.provision_local(workspace.id, OperatorId("admin"), OperatorRole.ADMIN)
        viewer = operators.provision_local(workspace.id, OperatorId("viewer"), OperatorRole.VIEWER)
    finally:
        group.close()
        accounts.close()
    server = create_server(HostConfig(canonical, identity))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, admin.value, viewer.value, str(goal.id), str(foreign_goal.id)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def request(
    port: int,
    method: str,
    path: str,
    body: dict[str, str] | None = None,
    cookie: str | None = None,
    origin: str | None = None,
    host: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": host or f"127.0.0.1:{port}"}
    if cookie:
        headers["Cookie"] = cookie
    if origin:
        headers["Origin"] = origin
        headers["X-Operator-Request"] = "1"
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body).encode()
    try:
        connection.request(method, path, payload, headers)
        result = connection.getresponse()
        return result.status, dict(result.getheaders()), result.read()
    finally:
        connection.close()


def login(port: int, credential: str) -> str:
    status, headers, data = request(
        port, "POST", "/api/v1/login", {"credential": credential}, origin=f"http://127.0.0.1:{port}"
    )
    assert status == 200, data
    assert "HttpOnly" in headers["Set-Cookie"] and "SameSite=Strict" in headers["Set-Cookie"]
    return headers["Set-Cookie"].split(";", 1)[0]


def test_host_auth_query_scope_and_escaping(site: tuple[int, str, str, str, str]) -> None:
    port, admin, viewer, goal, foreign_goal = site
    assert request(port, "GET", "/health/live")[0] == 200
    assert request(port, "GET", "/health/ready")[0] == 200
    assert request(port, "GET", "/api/v1/me")[0] == 401
    cookie = login(port, viewer)
    status, headers, payload = request(port, "GET", "/api/v1/inspect/goals", cookie=cookie)
    assert status == 200
    assert headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert json.loads(payload)["items"][0]["id"] == goal
    assert "secret foreign goal" not in payload.decode()
    assert request(port, "GET", "/api/v1/inspect/goals?id=" + foreign_goal, cookie=cookie)[0] == 404
    assert request(port, "GET", "/api/v1/inspect/goals?limit=101", cookie=cookie)[0] == 400
    assert request(port, "GET", "/api/v1/recovery", cookie=cookie)[0] == 403
    assert request(port, "GET", "/api/v1/operator-audit", cookie=cookie)[0] == 403
    assert request(port, "GET", "/", host="attacker.example")[0] == 403
    assert b"textContent" in request(port, "GET", "/console.js")[2]
    assert b"innerHTML" not in request(port, "GET", "/console.js")[2]
    assert (
        request(
            port,
            "POST",
            "/api/v1/mode/restrict",
            {"mode": "maintenance"},
            cookie=cookie,
            origin=f"http://127.0.0.1:{port}",
        )[0]
        == 403
    )
    admin_cookie = login(port, admin)
    assert (
        request(
            port,
            "POST",
            "/api/v1/mode/restrict",
            {"mode": "restore_quarantine"},
            cookie=admin_cookie,
        )[0]
        == 403
    )
    assert (
        request(
            port,
            "POST",
            "/api/v1/mode/restrict",
            {"mode": "restore_quarantine"},
            cookie=admin_cookie,
            origin="http://evil.example",
        )[0]
        == 403
    )
    assert (
        request(
            port,
            "POST",
            "/api/v1/mode/restrict",
            {"mode": "restore_quarantine"},
            cookie=admin_cookie,
            origin=f"http://127.0.0.1:{port}",
        )[0]
        == 200
    )
    assert (
        json.loads(request(port, "GET", "/api/v1/status", cookie=cookie)[2])["mode"]
        == "restore_quarantine"
    )
    assert request(port, "GET", "/api/v1/inspect/goals", cookie=cookie)[0] == 200
    assert (
        request(
            port, "POST", "/api/v1/logout", {}, cookie=cookie, origin=f"http://127.0.0.1:{port}"
        )[0]
        == 200
    )
    assert request(port, "GET", "/api/v1/me", cookie=cookie)[0] == 401


def test_aurora_fixture_uses_canonical_services(tmp_path: Path) -> None:
    path = tmp_path / "demo.sqlite"
    migrate_database(path)
    workspace = seed_aurora(path)
    group = SqliteStoreGroup(path)
    try:
        goals = group.domain.goals(workspace)
        assert {goal.status.value for goal in goals} == {"satisfied", "active"}
        assert len(group.domain.tasks_for_goal(goals[0].id)) >= 1
        assert len(group.runtime.definitions(workspace)) == 3
        assert len(group.organization.versions(workspace)[0].departments) == 3
        assert len(group.runtime.runs(workspace)) == 4
        assert len(group.runtime.governed_actions(workspace)) == 2
        assert len(SqliteInspectionCatalog(group).records(workspace, "invocations")) == 1
        assert len(SqliteInspectionCatalog(group).records(workspace, "receipts")) == 1
        assert len(SqliteInspectionCatalog(group).records(workspace, "knowledge")) == 1
    finally:
        group.close()


def test_operator_read_waits_for_canonical_commit(tmp_path: Path) -> None:
    canonical, identity = tmp_path / "canonical.sqlite", tmp_path / "identity.sqlite"
    migrate_database(canonical)
    migrate_operator_database(identity)
    writer, accounts = SqliteStoreGroup(canonical), SqliteOperatorStore(identity)
    clock, ids = FakeClock(datetime(2026, 9, 26, tzinfo=UTC)), DeterministicIdGenerator("race")
    domain = DomainService(writer.domain, clock, ids)
    workspace = domain.create_workspace("Concurrent reads")
    domain.create_goal(CreateGoalCommand(workspace.id, "Before", ("valid",)))
    operator = OperatorService(accounts, writer.domain, clock, SecureOperatorSecrets())
    token = operator.login(
        operator.provision_local(workspace.id, OperatorId("reader"), OperatorRole.VIEWER).value
    ).value
    started, done = ThreadEvent(), ThreadEvent()
    result: list[str] = []

    def reader() -> None:
        started.set()
        graph, identities = SqliteStoreGroup(canonical), SqliteOperatorStore(identity)
        try:
            service = OperatorService(identities, graph.domain, clock, SecureOperatorSecrets())
            tools = ToolRuntimeService(graph.runtime, graph.registry, clock, ids)
            queries = OperatorQueryService(
                service,
                graph.runtime,
                AuditQueryService(graph.runtime),
                RecoveryService(graph.runtime, tools, clock, ids),
            )
            result.extend(goal.objective for goal in queries.goals(token, workspace.id).items)
        finally:
            identities.close()
            graph.close()
            done.set()

    try:
        with writer.transaction():
            domain.create_goal(CreateGoalCommand(workspace.id, "After", ("valid",)))
            thread = Thread(target=reader)
            thread.start()
            assert started.wait(5)
            sleep(0.1)
            assert not done.is_set()
        thread.join(timeout=10)
        assert done.is_set()
        assert result == ["Before", "After"] or result == ["After", "Before"]
    finally:
        accounts.close()
        writer.close()
