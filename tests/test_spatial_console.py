"""Spatial UI acceptance against the real SQLite-backed loopback operator host.

The browser receives canonical records from Stage 11 HTTP endpoints. The empty
workspace is also real; neither path substitutes a standalone UI data fixture.
"""

import json
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass, field
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
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.application.operator import OperatorService
from agent_company_os.application.service import CreateGoalCommand, DomainService
from agent_company_os.domain.operator import OperatorId, OperatorRole
from agent_company_os.operator_cli import seed_aurora
from agent_company_os.operator_host import HostConfig, create_server
from test_operator_http import login, request

MARKER = "<script>alert('spatial-xss')</script><img src=x onerror=alert('spatial-xss')>"


@dataclass(frozen=True)
class SpatialSite:
    port: int
    credential: str = field(repr=False)
    root: Path
    populated: bool
    hostile_goal: str | None


@pytest.fixture(scope="module", params=[True, False], ids=["aurora", "empty"])
def spatial_site(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[SpatialSite]:
    populated = bool(request.param)
    root = tmp_path_factory.mktemp("spatial-aurora" if populated else "spatial-empty")
    canonical, identity = root / "canonical.sqlite", root / "identity.sqlite"
    migrate_database(canonical)
    migrate_operator_database(identity)
    workspace = seed_aurora(canonical, inspection_marker=MARKER) if populated else None
    group, accounts = SqliteStoreGroup(canonical), SqliteOperatorStore(identity)
    clock = SystemClock()
    hostile_goal = None
    try:
        domain = DomainService(group.domain, clock, DeterministicIdGenerator("spatial"))
        if workspace is None:
            workspace = domain.create_workspace("Empty company").id
        else:
            hostile_goal = str(
                domain.create_goal(CreateGoalCommand(workspace, MARKER, ("Review",))).id
            )
        operators = OperatorService(accounts, group.domain, clock, SecureOperatorSecrets())
        credential = operators.provision_local(
            workspace, OperatorId("spatial-admin"), OperatorRole.ADMIN
        ).value
    finally:
        accounts.close()
        group.close()
    server = create_server(HostConfig(canonical, identity))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield SpatialSite(server.server_port, credential, root, populated, hostile_goal)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_spatial_assets_keep_operator_security(spatial_site: SpatialSite) -> None:
    status, headers, body = request(spatial_site.port, "GET", "/command")
    assert status == 200
    assert b"/spatial.js" in body and b"/spatial.css" in body
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    assert "'unsafe-inline'" not in headers["Content-Security-Policy"]
    assert request(spatial_site.port, "GET", "/api/v1/me")[0] == 401
    for asset in ("spatial.js", "spatial.css", "audio.js"):
        result, asset_headers, content = request(spatial_site.port, "GET", "/" + asset)
        assert result == 200 and content, asset
        assert asset_headers["X-Content-Type-Options"] == "nosniff"
        if asset.endswith(".js"):
            assert b"innerHTML" not in content, asset
    cookie = login(spatial_site.port, spatial_site.credential)
    assert request(spatial_site.port, "GET", "/api/v1/inspect/agents", cookie=cookie)[0] == 200


def _browser_runtime() -> tuple[str, Path]:
    node = shutil.which("node")
    chrome = next(
        (
            path
            for path in (
                Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
                Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
                Path(shutil.which("chromium") or "/not-installed"),
            )
            if path.is_file()
        ),
        None,
    )
    if node is None or chrome is None:
        pytest.skip("Spatial browser acceptance needs local Node and Chromium")
    return node, chrome


def test_live_spatial_navigation_and_accessibility(spatial_site: SpatialSite) -> None:
    node, chrome = _browser_runtime()
    result = subprocess.run(
        [node, str(Path(__file__).parent / "fixtures/spatial_browser.mjs")],
        input=json.dumps(
            {
                "chrome": str(chrome),
                "profile": str(spatial_site.root / "browser-profile"),
                "snapshots": str(spatial_site.root / "snapshots"),
                "origin": f"http://127.0.0.1:{spatial_site.port}",
                "credential": spatial_site.credential,
                "marker": MARKER,
                "hostileGoal": spatial_site.hostile_goal,
                "populated": spatial_site.populated,
            }
        ),
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "spatial_browser_acceptance_passed" in result.stdout
