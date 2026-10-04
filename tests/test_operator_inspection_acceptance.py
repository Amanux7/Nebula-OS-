# mypy: disable-error-code="no-untyped-call,no-untyped-def"
"""Canonical inspection, decode limits and live HTTP acceptance."""

import json
import shutil
import sqlite3
import subprocess
from pathlib import Path
from threading import Thread

import pytest

from agent_company_os.adapters.clocks import SystemClock
from agent_company_os.adapters.ids import DeterministicIdGenerator
from agent_company_os.adapters.operator_store import (
    SecureOperatorSecrets,
    SqliteOperatorStore,
    migrate_operator_database,
)
from agent_company_os.adapters.sqlite_database import migrate_database
from agent_company_os.adapters.sqlite_inspection import COLLECTIONS
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.application.operator import OperatorService
from agent_company_os.application.service import CreateGoalCommand, DomainService
from agent_company_os.domain.errors import InvariantViolation
from agent_company_os.domain.events import Event, EventType
from agent_company_os.domain.ids import EventId
from agent_company_os.domain.operator import OperatorId, OperatorRole
from agent_company_os.domain.transitions import SubjectType
from agent_company_os.operator_cli import seed_aurora
from agent_company_os.operator_host import HostConfig, create_server
from test_operator_http import login, request

MARKER = "<script>alert(1)</script><img src=x onerror=alert(1)>"


@pytest.fixture(scope="module")
def complete_site(tmp_path_factory):
    root = tmp_path_factory.mktemp("inspection")
    path, identity = root / "app.sqlite", root / "identity.sqlite"
    migrate_database(path)
    migrate_operator_database(identity)
    ws = seed_aurora(path, inspection_marker=MARKER)
    graph, accounts = SqliteStoreGroup(path), SqliteOperatorStore(identity)
    clock = SystemClock()
    try:
        domain = DomainService(graph.domain, clock, DeterministicIdGenerator("inspection"))
        goal = domain.create_goal(CreateGoalCommand(ws, MARKER, ("review",)))
        run = graph.runtime.runs(ws)[0]
        with graph.transaction():
            graph.runtime.append_event(
                Event(
                    EventId("inspection-safe-metadata"),
                    ws,
                    EventType.RECOVERY_DETECTED,
                    SubjectType.AGENT_RUN,
                    str(run.id),
                    run.version,
                    clock.now(),
                    (("reason_code", MARKER), ("goal_id", str(goal.id))),
                )
            )
        operators = OperatorService(accounts, graph.domain, clock, SecureOperatorSecrets())
        credential = operators.provision_local(ws, OperatorId("acceptance"), OperatorRole.ADMIN)
    finally:
        accounts.close()
        graph.close()
    server = create_server(HostConfig(path, identity))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, credential.value, str(goal.id), root
    finally:
        server.shutdown()
        thread.join(5)
        server.server_close()


def test_complete_http_dtos_lineage_and_protected_content(complete_site):
    port, credential, _goal, _root = complete_site
    cookie = login(port, credential)
    records = {}
    for kind in (*COLLECTIONS, "departments"):
        status, _, body = request(port, "GET", f"/api/v1/inspect/{kind}?limit=100", cookie=cookie)
        assert status == 200, (kind, body)
        records[kind] = json.loads(body)["items"]
        assert records[kind], kind
        for row in records[kind]:
            assert set(row) == {"id", "kind", "fields", "links"}
        if kind in ("results", "runs", "receipts", "intents", "approvals"):
            assert MARKER not in body.decode()  # protected result text omitted, not rendered
    for rows in records.values():
        for row in rows:
            for link in row["links"]:
                assert link["id"] in {r["id"] for r in records[link["kind"]]}, link
    goal = next(r for r in records["goals"] if "cross-department" in dict(r["fields"])["objective"])
    status, _, body = request(port, "GET", "/api/v1/lineage/goals/" + goal["id"], cookie=cookie)
    assert status == 200
    sections = {s["kind"]: s["records"] for s in json.loads(body)["sections"]}
    assert {
        "tasks",
        "runs",
        "orchestrations",
        "plans",
        "materializations",
        "delegations",
        "delegation_attempts",
        "results",
        "messages",
        "threads",
        "handoffs",
    } <= sections.keys()
    for row in records["runs"]:
        fields = dict(row["fields"])
        assert {
            "working_state.iteration",
            "deadline",
            "tool_call_count",
            "observation_count",
        } <= fields.keys()
        assert any(link["kind"] == "agent_versions" for link in row["links"])
    intent = next(r for r in records["intents"] if dict(r["fields"])["consumed"] == "True")
    body = request(port, "GET", "/api/v1/lineage/intents/" + intent["id"], cookie=cookie)[2]
    assert {"approval_requests", "approval_decisions", "invocations", "receipts"} <= {
        s["kind"] for s in json.loads(body)["sections"]
    }
    receipt = records["receipts"][0]
    assert dict(receipt["fields"])["outcome_certainty"] == "observed_success"
    assert dict(receipt["fields"])["invocation.tool_version.definition.risk"] == "external_write"
    assert any(link["kind"] == "invocations" for link in receipt["links"])


@pytest.mark.parametrize("damage", ["rows", "record_bytes"])
def test_inspection_rejects_capacity_before_codec(tmp_path, monkeypatch, damage):
    path = tmp_path / "capacity.sqlite"
    migrate_database(path)
    graph = SqliteStoreGroup(path)
    domain = DomainService(graph.domain, SystemClock(), DeterministicIdGenerator())
    ws = domain.create_workspace("Bounded")
    domain.create_goal(CreateGoalCommand(ws.id, "Bounded goal", ("valid",)))
    graph.close()
    if damage == "record_bytes":
        connection = sqlite3.connect(path)
        connection.execute(
            "UPDATE domain_records SET payload=? WHERE kind='goal'",
            (json.dumps({"oversized": "x" * 1048576}),),
        )
        connection.commit()
        connection.close()

    def forbidden_decode(*args, **kwargs):
        pytest.fail("Capacity must be rejected before decoding")

    monkeypatch.setattr("agent_company_os.adapters.sqlite_store.decode_record", forbidden_decode)
    with pytest.raises(InvariantViolation, match="inspection_capacity_exceeded"):
        SqliteStoreGroup(path, inspection_limit=1 if damage == "rows" else 10000)


def test_live_browser_csp_stored_xss_and_navigation(complete_site):
    port, credential, goal, root = complete_site
    node = shutil.which("node")
    chrome = next(
        (
            p
            for p in (
                Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
                Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
                Path(shutil.which("chromium") or "/not-installed"),
            )
            if p.is_file()
        ),
        None,
    )
    if node is None or chrome is None:
        pytest.skip("Local browser acceptance needs Node and Chromium; no runtime dependency")
    result = subprocess.run(
        [node, str(Path(__file__).parent / "fixtures/operator_browser.mjs")],
        input=json.dumps(
            {
                "chrome": str(chrome),
                "profile": str(root / "browser-profile"),
                "origin": f"http://127.0.0.1:{port}",
                "credential": credential,
                "marker": MARKER,
                "goal": goal,
            }
        ),
        text=True,
        capture_output=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "browser_acceptance_passed" in result.stdout
