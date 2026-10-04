"""Loopback-only Stage 11 operator inspection host.

Each request owns its SQLite connections. Only explicitly listed application
queries are reachable; no agent worker or Tool executor is started here.
"""

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import Enum
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from agent_company_os.adapters.clocks import SystemClock
from agent_company_os.adapters.ids import SystemIdGenerator
from agent_company_os.adapters.operational_store import SqliteOperationalStore
from agent_company_os.adapters.operator_store import SecureOperatorSecrets, SqliteOperatorStore
from agent_company_os.adapters.sqlite_inspection import COLLECTIONS, SqliteInspectionCatalog
from agent_company_os.adapters.sqlite_store import SqliteStoreGroup
from agent_company_os.application.audit import AuditQueryService
from agent_company_os.application.operations import OperationalModeService
from agent_company_os.application.operator import OperatorService
from agent_company_os.application.operator_queries import OperatorQueryService
from agent_company_os.application.recovery import RecoveryService
from agent_company_os.application.tool_runtime import ToolRuntimeService
from agent_company_os.domain.errors import DomainError, EntityNotFound, InvariantViolation
from agent_company_os.domain.ids import GoalId, OpaqueId, Version
from agent_company_os.domain.operations import OperationalMode
from agent_company_os.domain.operator import (
    AuthenticationDenied,
    OperatorAccessDenied,
    OperatorResource,
)


@dataclass(frozen=True)
class HostConfig:
    canonical_db: Path
    identity_db: Path
    port: int = 0
    bind: str = "127.0.0.1"
    inspection_limit: int = 10_000

    def __post_init__(self) -> None:
        if self.bind != "127.0.0.1" or type(self.port) is not int or not 0 <= self.port <= 65535:
            raise InvariantViolation("operator_host_loopback_only")
        if self.canonical_db.resolve() == self.identity_db.resolve():
            raise InvariantViolation("operator_identity_must_be_separate")
        if type(self.inspection_limit) is not int or not 1 <= self.inspection_limit <= 10_000:
            raise InvariantViolation("inspection_limit_invalid")


@dataclass
class _Services:
    group: SqliteStoreGroup
    identity: SqliteOperatorStore
    operator: OperatorService
    queries: OperatorQueryService
    modes: OperationalModeService


@contextmanager
def _services(config: HostConfig) -> Iterator[_Services]:
    group = SqliteStoreGroup(config.canonical_db, inspection_limit=config.inspection_limit)
    try:
        identity = SqliteOperatorStore(config.identity_db)
        try:
            clock, ids = SystemClock(), SystemIdGenerator()
            operator = OperatorService(identity, group.domain, clock, SecureOperatorSecrets())
            tools = ToolRuntimeService(group.runtime, group.registry, clock, ids)
            recovery = RecoveryService(group.runtime, tools, clock, ids, group.orchestration)
            audit = AuditQueryService(
                group.runtime,
                (group.knowledge, group.memory, group.communication),
                group.orchestration,
            )
            queries = OperatorQueryService(
                operator, group.runtime, audit, recovery, SqliteInspectionCatalog(group)
            )
            yield _Services(
                group,
                identity,
                operator,
                queries,
                OperationalModeService(operator, SqliteOperationalStore(group), recovery),
            )
        finally:
            identity.close()
    finally:
        group.close()


def _json_safe(value: Any) -> Any:
    if isinstance(value, OpaqueId):
        return str(value)
    if isinstance(value, Version):
        return value.value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json_safe(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if value is None or type(value) in (str, int, bool, float):
        return value
    raise InvariantViolation("unsupported_http_projection")


class _OperatorHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 8

    def __init__(self, config: HostConfig) -> None:
        self.config = config
        self._login_lock = Lock()
        self._login_failures: dict[str, list[float]] = {}
        self._workers = BoundedSemaphore(4)
        self._metrics_lock = Lock()
        self.metrics: dict[str, int | float] = {
            "requests": 0,
            "authentication_failures": 0,
            "authorization_failures": 0,
            "request_duration_ms": 0.0,
            "query_duration_ms": 0.0,
            "responses_2xx": 0,
            "responses_4xx": 0,
            "responses_5xx": 0,
        }
        started = monotonic()
        self.workspace_startup: dict[str, dict[str, Any]] = {}
        # Opening every canonical collection now catches a corrupt DB before binding.
        with _services(config) as services:
            for workspace in services.group.domain.workspaces():
                self.workspace_startup[str(workspace.id)] = {
                    "recovery_count": len(services.queries.recovery.classify(workspace.id)),
                    "mode": services.group.runtime.operational_mode(workspace.id).value,
                }
            schema = services.group.connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0]
        self.startup = {
            "duration_ms": round((monotonic() - started) * 1000, 3),
            "database_open": "ok",
            "canonical_schema": schema,
            "identity_schema": 1,
        }
        super().__init__((config.bind, config.port), _OperatorHandler)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._workers.acquire(timeout=1):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._workers.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._workers.release()

    def metric(self, name: str, value: int | float = 1) -> None:
        with self._metrics_lock:
            self.metrics[name] += value

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"

    def login_allowed(self, client: str) -> bool:
        with self._login_lock:
            now = monotonic()
            # One bounded loopback bucket, charged before auth to avoid racing failures.
            previous = [t for t in self._login_failures.get("loopback", ()) if now - t < 60]
            allowed = len(previous) < 5
            if allowed:
                previous.append(now)
            self._login_failures = {"loopback": previous}
            return allowed


class _OperatorHandler(BaseHTTPRequestHandler):
    server: _OperatorHTTPServer
    server_version = "AgentCompanyOperator/0.1"
    sys_version = ""

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format: str, *args: object) -> None:
        # Default logger includes URL, which may contain a guessed ID or token.
        return

    def _send(
        self,
        status: int,
        value: Any,
        *,
        cookie: str | None = None,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        payload = (
            json.dumps(_json_safe(value), separators=(",", ":")).encode("utf-8")
            if content_type.startswith("application/json")
            else value
        )
        self.send_response(status)
        category = (
            "responses_2xx"
            if status < 400
            else "responses_4xx"
            if status < 500
            else "responses_5xx"
        )
        self.server.metric(category)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        )
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, status: int, code: str) -> None:
        self._send(status, {"error": {"code": code}})

    def _guard(self, mutation: bool = False) -> None:
        for name in ("Host", "Origin", "X-Operator-Request", "Content-Type", "Content-Length"):
            if len(self.headers.get_all(name, [])) > 1:
                raise OperatorAccessDenied()
        if self.headers.get("Transfer-Encoding") is not None:
            raise InvariantViolation("transfer_encoding_unsupported")
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            raise OperatorAccessDenied()
        if len(self.path) > 2048 or len(self.headers.as_bytes()) > 8192:
            raise InvariantViolation("request_too_large")
        origin = self.headers.get("Origin")
        if origin is not None and origin != self.server.origin:
            raise OperatorAccessDenied()
        if mutation and (
            origin != self.server.origin or self.headers.get("X-Operator-Request") != "1"
        ):
            raise OperatorAccessDenied()

    def _token(self) -> str:
        cookies = self.headers.get_all("Cookie", [])
        if len(cookies) != 1:
            raise AuthenticationDenied()
        matches = [item[13:] for item in cookies[0].split("; ") if item.startswith("operator_sid=")]
        if len(matches) != 1:
            raise AuthenticationDenied()
        return matches[0]

    def _body(self) -> dict[str, Any]:
        if self.headers.get("Content-Type") != "application/json":
            raise InvariantViolation("invalid_content_type")
        raw_length = self.headers.get("Content-Length", "")
        if not raw_length.isdecimal() or int(raw_length) > 4096:
            raise InvariantViolation("invalid_content_length")
        try:
            data = json.loads(self.rfile.read(int(raw_length)))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise InvariantViolation("invalid_json_body") from None
        if not isinstance(data, dict):
            raise InvariantViolation("invalid_json_body")
        return data

    def _handle(self, mutation: bool) -> None:
        started = monotonic()
        self.server.metric("requests")
        try:
            self._guard(mutation)
            path = urlsplit(self.path)
            if path.fragment or len(path.query) > 512:
                raise InvariantViolation("invalid_query")
            parsed = parse_qs(path.query, strict_parsing=True, max_num_fields=8)
            if any(len(values) != 1 for values in parsed.values()):
                raise InvariantViolation("duplicate_query_parameter")
            query = {key: value[0] for key, value in parsed.items()}
            if mutation:
                if query:
                    raise InvariantViolation("mutation_query_unsupported")
                self._post(path.path)
            else:
                self._get(path.path, query)
        except AuthenticationDenied:
            self.server.metric("authentication_failures")
            self._error(HTTPStatus.UNAUTHORIZED, "authentication_required")
        except OperatorAccessDenied:
            self.server.metric("authorization_failures")
            self._error(HTTPStatus.FORBIDDEN, "access_denied")
        except EntityNotFound:
            self._error(HTTPStatus.NOT_FOUND, "not_found")
        except DomainError as error:
            if error.details.get("rule") == "inspection_capacity_exceeded":
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "inspection_capacity_exceeded")
            else:
                self._error(HTTPStatus.BAD_REQUEST, error.code)
        except (ValueError, KeyError):
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request")
        except (ConnectionError, TimeoutError):
            # A disconnected local browser cannot receive a second error response.
            return
        except (sqlite3.Error, OSError):
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable")
        finally:
            duration = (monotonic() - started) * 1000
            self.server.metric("request_duration_ms", duration)
            if not mutation:
                self.server.metric("query_duration_ms", duration)

    def do_GET(self) -> None:
        self._handle(False)

    def do_POST(self) -> None:
        self._handle(True)

    def do_PUT(self) -> None:
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed")

    def do_DELETE(self) -> None:
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed")

    def _get(self, path: str, query: dict[str, str]) -> None:
        if path == "/health/live":
            self._send(200, {"alive": True})
            return
        if path == "/health/ready":
            with _services(self.server.config) as services:
                services.group.domain.workspaces()
            self._send(200, {"ready": True})
            return
        assets = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/command": ("command.html", "text/html; charset=utf-8"),
            "/spatial.js": ("spatial.js", "text/javascript; charset=utf-8"),
            "/spatial-data.js": ("spatial-data.js", "text/javascript; charset=utf-8"),
            "/spatial-core.js": ("spatial-core.js", "text/javascript; charset=utf-8"),
            "/audio.js": ("audio.js", "text/javascript; charset=utf-8"),
            "/spatial.css": ("spatial.css", "text/css; charset=utf-8"),
            "/console.js": ("console.js", "text/javascript; charset=utf-8"),
            "/console.css": ("console.css", "text/css; charset=utf-8"),
        }
        if path in assets:
            name, mime = assets[path]
            content = (Path(__file__).with_name("operator_ui") / name).read_bytes()
            self._send(200, content, content_type=mime)
            return
        if not path.startswith("/api/v1/"):
            self._error(404, "not_found")
            return
        token = self._token()
        with _services(self.server.config) as services:
            principal = services.operator.principal(token)
            workspace = principal.workspace_id
            if path == "/api/v1/me":
                self._send(
                    200,
                    {
                        "id": str(principal.id),
                        "workspace_id": str(workspace),
                        "role": principal.role.value,
                    },
                )
            elif path == "/api/v1/status":
                mode = services.modes.status(token, workspace)
                self._send(
                    200,
                    {
                        "mode": mode.value,
                        "recovery_count": len(services.queries.recovery.classify(workspace)),
                    },
                )
            elif path.startswith("/api/v1/inspect/"):
                kind = path.removeprefix("/api/v1/inspect/")
                if kind not in COLLECTIONS and kind != "departments":
                    raise EntityNotFound("Category", kind)
                if set(query) - {"limit", "cursor", "id", "goal_id"}:
                    raise InvariantViolation("invalid_inspection_filter")
                limit = int(query.get("limit", "25"))
                page = services.queries.inspect(
                    token,
                    workspace,
                    kind,
                    limit=limit,
                    cursor=query.get("cursor"),
                    entity_id=query.get("id"),
                    goal_id=query.get("goal_id"),
                )
                self._send(200, page)
            elif path == "/api/v1/recovery":
                if set(query) - {"limit", "cursor"}:
                    raise InvariantViolation("invalid_query")
                self._send(
                    200,
                    services.queries.recovery_incidents(
                        token,
                        workspace,
                        limit=int(query.get("limit", "25")),
                        cursor=query.get("cursor"),
                    ),
                )
            elif re.fullmatch(r"/api/v1/lineage/[^/]+/[^/]{1,768}", path):
                if query:
                    raise InvariantViolation("invalid_query")
                category, identifier = path.removeprefix("/api/v1/lineage/").split("/", 1)
                self._send(
                    200, services.queries.lineage(token, workspace, category, unquote(identifier))
                )
            elif path == "/api/v1/restore":
                self._send(
                    200,
                    {
                        "context": services.modes.context(token, workspace),
                        "release_attempts": services.modes.audit(token, workspace),
                    },
                )
            elif path == "/api/v1/diagnostics":
                services.operator.authorize(token, workspace, OperatorResource.ACCOUNT_ADMIN)
                with self.server._metrics_lock:
                    metrics = dict(self.server.metrics)
                self._send(
                    200,
                    {
                        "startup": {
                            **self.server.startup,
                            **self.server.workspace_startup.get(str(workspace), {}),
                        },
                        "requests": metrics,
                        "inspection_max_records": self.server.config.inspection_limit,
                        "inspection_max_bytes": 32 * 1024 * 1024,
                    },
                )
            elif re.fullmatch(r"/api/v1/audit/goals/[^/]{1,256}", path):
                if set(query) - {"limit", "cursor"}:
                    raise InvariantViolation("invalid_query")
                goal = GoalId(path.rsplit("/", 1)[1])
                self._send(
                    200,
                    services.queries.goal_timeline(
                        token,
                        workspace,
                        goal,
                        limit=int(query.get("limit", "25")),
                        cursor=query.get("cursor"),
                    ),
                )
            elif path == "/api/v1/operator-audit":
                services.operator.authorize(token, workspace, OperatorResource.AUDIT)
                audits = services.operator.audit(token, workspace)
                self._send(
                    200,
                    {
                        "items": [
                            {
                                "principal_id": str(a.principal_id),
                                "command": a.command,
                                "target_id": str(a.target_id),
                                "timestamp": a.timestamp.isoformat(),
                            }
                            for a in audits[:100]
                        ],
                        "truncated": len(audits) > 100,
                    },
                )
            else:
                self._error(404, "not_found")

    def _post(self, path: str) -> None:
        with _services(self.server.config) as services:
            if path == "/api/v1/login":
                if not self.server.login_allowed(self.client_address[0]):
                    self._error(HTTPStatus.TOO_MANY_REQUESTS, "login_rate_limited")
                    return
                body = self._body()
                if set(body) != {"credential"} or type(body["credential"]) is not str:
                    raise InvariantViolation("invalid_login_body")
                token = services.operator.login(body["credential"]).value
                self._send(
                    200,
                    {"authenticated": True},
                    cookie=(f"operator_sid={token}; HttpOnly; SameSite=Strict; Path=/api/v1"),
                )
                return
            token = self._token()
            if path == "/api/v1/logout":
                services.operator.logout(token)
                self._send(
                    200,
                    {"authenticated": False},
                    cookie=("operator_sid=; HttpOnly; SameSite=Strict; Path=/api/v1; Max-Age=0"),
                )
            elif path == "/api/v1/mode/restrict":
                body = self._body()
                if set(body) != {"mode"} or body["mode"] not in (
                    "maintenance",
                    "restore_quarantine",
                ):
                    raise InvariantViolation("invalid_operational_mode")
                principal = services.operator.principal(token)
                services.modes.restrict(
                    token, principal.workspace_id, OperationalMode(body["mode"])
                )
                self._send(
                    200, {"mode": services.modes.status(token, principal.workspace_id).value}
                )
            elif path == "/api/v1/mode/release":
                if self._body() != {}:
                    raise InvariantViolation("release_body_must_be_empty")
                principal = services.operator.principal(token)
                result = services.modes.release(token, principal.workspace_id)
                self._send(
                    200 if result.success else 403 if result.reason == "admin_required" else 409,
                    result,
                )
            else:
                self._error(404, "not_found")


def create_server(config: HostConfig) -> ThreadingHTTPServer:
    return _OperatorHTTPServer(config)
