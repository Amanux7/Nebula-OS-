"""Operator authentication uses real SQLite identity records and injected time/entropy."""

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_company_os.adapters.clocks import FakeClock
from agent_company_os.adapters.ids import DeterministicIdGenerator
from agent_company_os.adapters.operator_store import (
    SecureOperatorSecrets,
    SqliteOperatorStore,
    migrate_operator_database,
)
from agent_company_os.adapters.sqlite_database import migrate_database
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.application.audit import AuditQueryService
from agent_company_os.application.operator import OperatorService
from agent_company_os.application.operator_queries import OperatorQueryService
from agent_company_os.application.recovery import RecoveryService
from agent_company_os.application.service import CreateGoalCommand, CreateTaskCommand, DomainService
from agent_company_os.application.tool_runtime import ToolRuntimeService
from agent_company_os.domain.errors import EntityNotFound, InvariantViolation, VersionConflict
from agent_company_os.domain.ids import Version, WorkspaceId
from agent_company_os.domain.operator import (
    AuthenticationDenied,
    OperatorAccessDenied,
    OperatorId,
    OperatorResource,
    OperatorRole,
)


class TestSecrets:
    __test__ = False

    def __init__(self) -> None:
        self.counter = 0

    def issue(self) -> str:
        self.counter += 1
        return f"{self.counter:064x}"


@dataclass
class Harness:
    group: SqliteStoreGroup
    store: SqliteOperatorStore
    service: OperatorService
    clock: FakeClock
    domain: DomainService
    workspace: WorkspaceId
    foreign: WorkspaceId
    queries: OperatorQueryService
    path: Path

    def login(self, name: str, role: OperatorRole = OperatorRole.VIEWER) -> str:
        credential = self.service.provision_local(self.workspace, OperatorId(name), role)
        return self.service.login(credential.value).value


@pytest.fixture
def operator(tmp_path: Path) -> Iterator[Harness]:
    canonical, identity = tmp_path / "canonical.sqlite", tmp_path / "identity.sqlite"
    migrate_database(canonical)
    migrate_operator_database(identity)
    group, store = SqliteStoreGroup(canonical), SqliteOperatorStore(identity)
    clock = FakeClock(datetime(2026, 9, 21, tzinfo=UTC))
    ids = DeterministicIdGenerator("operator-tests")
    domain = DomainService(group.domain, clock, ids)
    workspace, foreign = domain.create_workspace("Aurora"), domain.create_workspace("Foreign")
    service = OperatorService(store, group.domain, clock, TestSecrets(), 60)
    recovery = RecoveryService(
        group.runtime, ToolRuntimeService(group.runtime, group.registry, clock, ids), clock, ids
    )
    queries = OperatorQueryService(
        service, group.runtime, AuditQueryService(group.runtime), recovery
    )
    try:
        yield Harness(
            group, store, service, clock, domain, workspace.id, foreign.id, queries, identity
        )
    finally:
        store.close()
        group.close()


def test_login_secrets_not_persisted_or_represented(operator: Harness) -> None:
    h = operator
    credential = h.service.provision_local(h.workspace, OperatorId("viewer"), OperatorRole.VIEWER)
    session = h.service.login(credential.value)
    assert credential.value not in repr(credential)
    assert session.value not in repr(session)
    dump = "\n".join(h.store.connection.iterdump())
    assert credential.value not in dump and session.value not in dump
    principal = h.service.authorize(session.value, h.workspace, OperatorResource.OPERATIONAL)
    assert principal.id == OperatorId("viewer")
    with pytest.raises(AuthenticationDenied):
        h.service.authorize(credential.value, h.workspace, OperatorResource.OPERATIONAL)
    with pytest.raises(AuthenticationDenied):
        h.service.login(session.value)


@pytest.mark.parametrize(
    "token", ["", "viewer", "admin", "x" * 64, "f" * 64, "0" * 65, "' OR 1=1 --"]
)
def test_forged_authentication_denied(operator: Harness, token: str) -> None:
    with pytest.raises(AuthenticationDenied):
        operator.service.login(token)
    with pytest.raises(AuthenticationDenied):
        operator.queries.goals(token, operator.workspace)


@pytest.mark.parametrize("role", list(OperatorRole))
def test_role_scope_and_sensitive_denial(operator: Harness, role: OperatorRole) -> None:
    h = operator
    token = h.login(role.value, role)
    h.service.authorize(token, h.workspace, OperatorResource.OPERATIONAL)
    with pytest.raises(OperatorAccessDenied):
        h.service.authorize(token, h.foreign, OperatorResource.OPERATIONAL)
    with pytest.raises(OperatorAccessDenied):
        h.service.authorize(token, h.workspace, OperatorResource.SENSITIVE)
    if role is OperatorRole.VIEWER:
        with pytest.raises(OperatorAccessDenied):
            h.queries.recovery_cases(token, h.workspace)
    else:
        assert h.queries.recovery_cases(token, h.workspace).items == ()
    if role is not OperatorRole.ADMIN:
        with pytest.raises(OperatorAccessDenied):
            h.service.disable(token, h.workspace, OperatorId(role.value), Version(1))


def test_session_expiry_logout_and_reopen(operator: Harness) -> None:
    h = operator
    token = h.login("viewer")
    reopened = SqliteOperatorStore(h.path)
    service = OperatorService(reopened, h.group.domain, h.clock, TestSecrets())
    try:
        service.authorize(token, h.workspace, OperatorResource.OPERATIONAL)
        h.clock.advance(timedelta(seconds=60))
        with pytest.raises(AuthenticationDenied):
            service.authorize(token, h.workspace, OperatorResource.OPERATIONAL)
    finally:
        reopened.close()
    token = h.login("second")
    h.service.logout(token)
    with pytest.raises(AuthenticationDenied):
        h.service.authorize(token, h.workspace, OperatorResource.OPERATIONAL)


def test_disable_revokes_existing_sessions_atomically(
    operator: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = operator
    admin = h.login("admin", OperatorRole.ADMIN)
    viewer = h.login("viewer")
    original = h.store.append_audit

    def unavailable(*args: object) -> None:
        raise RuntimeError("injected audit fault")

    monkeypatch.setattr(h.store, "append_audit", unavailable)
    with pytest.raises(RuntimeError):
        h.service.disable(admin, h.workspace, OperatorId("viewer"), Version(1))
    h.service.authorize(viewer, h.workspace, OperatorResource.OPERATIONAL)
    monkeypatch.setattr(h.store, "append_audit", original)
    h.service.disable(admin, h.workspace, OperatorId("viewer"), Version(1))
    with pytest.raises(AuthenticationDenied):
        h.service.authorize(viewer, h.workspace, OperatorResource.OPERATIONAL)
    with pytest.raises(VersionConflict):
        h.service.disable(admin, h.workspace, OperatorId("viewer"), Version(1))
    assert [e.command for e in h.service.audit(admin, h.workspace)].count("disabled") == 1
    with pytest.raises(sqlite3.IntegrityError):
        h.store.connection.execute("DELETE FROM operator_audit")


def test_bootstrap_migration_is_separate_idempotent_and_checked(
    operator: Harness, tmp_path: Path
) -> None:
    migrate_operator_database(operator.path)
    with pytest.raises(InvariantViolation):
        migrate_operator_database(tmp_path / "canonical.sqlite")
    operator.store.connection.execute("UPDATE operator_schema SET checksum='invalid'")
    with pytest.raises(InvariantViolation):
        SqliteOperatorStore(operator.path)
    with pytest.raises(InvariantViolation):
        migrate_operator_database(operator.path)


def test_unknown_account_role_rejected(operator: Harness) -> None:
    token = operator.login("viewer")
    operator.store.connection.execute("PRAGMA ignore_check_constraints=ON")
    operator.store.connection.execute("UPDATE operator_accounts SET role='superuser'")
    with pytest.raises(InvariantViolation):
        operator.service.authorize(token, operator.workspace, OperatorResource.OPERATIONAL)


def test_goal_pages_and_foreign_task(operator: Harness) -> None:
    h = operator
    token = h.login("auditor", OperatorRole.AUDITOR)
    goals = [
        h.domain.create_goal(CreateGoalCommand(h.workspace, f"Outcome {i}", ("evidence",)))
        for i in range(7)
    ]
    foreign_goal = h.domain.create_goal(CreateGoalCommand(h.foreign, "Secret", ("evidence",)))
    h.domain.activate_goal(foreign_goal.id, foreign_goal.version)
    foreign_task = h.domain.create_task(
        CreateTaskCommand(h.foreign, foreign_goal.id, "Secret task", ("evidence",))
    )
    seen: list[str] = []
    cursor = None
    while True:
        page = h.queries.goals(token, h.workspace, limit=3, cursor=cursor)
        seen.extend(g.id for g in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == sorted(str(g.id) for g in goals)
    assert len(set(seen)) == 7
    with pytest.raises(EntityNotFound):
        h.queries.task(token, h.workspace, foreign_task.id)
    with pytest.raises(OperatorAccessDenied):
        h.queries.goals(token, h.foreign)
    assert h.queries.goal_timeline(token, h.workspace, goals[0].id).items


@pytest.mark.parametrize("cursor", ["-1", "00", "", "1.5", "１００", "1000001", "x" * 1000])
def test_invalid_cursor(operator: Harness, cursor: str) -> None:
    token = operator.login("viewer")
    with pytest.raises(InvariantViolation):
        operator.queries.goals(token, operator.workspace, cursor=cursor)


@pytest.mark.parametrize("limit", [0, -1, 101, True])
def test_page_limit(operator: Harness, limit: int) -> None:
    token = operator.login("viewer")
    with pytest.raises(InvariantViolation):
        operator.queries.goals(token, operator.workspace, limit=limit)


def test_production_entropy_is_not_deterministic() -> None:
    entropy = SecureOperatorSecrets()
    first, second = entropy.issue(), entropy.issue()
    assert len(first) == len(second) == 64 and first != second


def test_identity_survives_discarded_service_graph(tmp_path: Path) -> None:
    canonical, identity = tmp_path / "state.sqlite", tmp_path / "operators.sqlite"
    migrate_database(canonical)
    migrate_operator_database(identity)
    instant = datetime(2026, 9, 21, tzinfo=UTC)

    def first_process() -> tuple[WorkspaceId, str, str]:
        group, store = SqliteStoreGroup(canonical), SqliteOperatorStore(identity)
        clock = FakeClock(instant)
        domain = DomainService(group.domain, clock, DeterministicIdGenerator())
        ws = domain.create_workspace("Persisted")
        service = OperatorService(store, group.domain, clock, TestSecrets(), 30)
        credential = service.provision_local(ws.id, OperatorId("auditor"), OperatorRole.AUDITOR)
        token = service.login(credential.value)
        store.close()
        group.close()
        return ws.id, credential.value, token.value

    workspace, credential, token = first_process()
    group, store = SqliteStoreGroup(canonical), SqliteOperatorStore(identity)
    try:
        clock = FakeClock(instant + timedelta(seconds=29))
        service = OperatorService(store, group.domain, clock, SecureOperatorSecrets())
        assert (
            service.authorize(token, workspace, OperatorResource.AUDIT).role is OperatorRole.AUDITOR
        )
        clock.advance(timedelta(seconds=1))
        with pytest.raises(AuthenticationDenied):
            service.authorize(token, workspace, OperatorResource.AUDIT)
        # A new login does not reinterpret or extend the old session deadline.
        new = service.login(credential)
        assert new.value != token
        with pytest.raises(AuthenticationDenied):
            service.authorize(token, workspace, OperatorResource.AUDIT)
    finally:
        store.close()
        group.close()


def test_denial_precedes_canonical_read(operator: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_read() -> None:
        raise AssertionError("must authenticate before canonical access")

    monkeypatch.setattr(operator.group.runtime, "atomic", forbidden_read)
    with pytest.raises(AuthenticationDenied):
        operator.queries.goals("f" * 64, operator.workspace)


def test_session_creation_audit_failure_rolls_back(
    operator: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = operator
    credential = h.service.provision_local(h.workspace, OperatorId("viewer"), OperatorRole.VIEWER)

    def failure(*args: object) -> None:
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(h.store, "append_audit", failure)
    with pytest.raises(RuntimeError):
        h.service.login(credential.value)
    assert h.store.connection.execute("SELECT count(*) FROM operator_sessions").fetchone() == (0,)


def test_guessed_foreign_account_cannot_be_disabled(operator: Harness) -> None:
    h = operator
    token = h.login("admin", OperatorRole.ADMIN)
    h.service.provision_local(h.foreign, OperatorId("foreign"), OperatorRole.VIEWER)
    with pytest.raises(OperatorAccessDenied):
        h.service.disable(token, h.workspace, OperatorId("foreign"), Version(1))
    with pytest.raises(OperatorAccessDenied):
        h.service.disable(token, h.workspace, OperatorId("nonexistent"), Version(1))
    account = h.store.account(OperatorId("foreign"))
    assert account is not None and account.principal.enabled
