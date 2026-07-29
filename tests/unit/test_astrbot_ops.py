import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "rag-stack" / "scripts" / "astrbot_ops.py"
COOGEN_FIXTURE = (
    Path(__file__).parents[2] / "rag-stack" / "fixtures" / "coogen-astrbot-recovery"
)


def run_ops(tmp_path: Path, fixture: dict, *args: str) -> subprocess.CompletedProcess:
    """Run the public operations CLI against a secret-free fixture.

    Args:
        tmp_path: Temporary directory for the fixture.
        fixture: Boundary state consumed by the verifier.
        *args: Extra CLI arguments.

    Returns:
        Completed subprocess result.
    """
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "verify",
            "--fixture",
            str(fixture_path),
            "--json",
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def run_recovery(
    tmp_path: Path, fixture: dict, *args: str
) -> subprocess.CompletedProcess:
    """Run the public QQ recovery command against a fixture.

    Args:
        tmp_path: Temporary directory for the fixture.
        fixture: Recovery observations.
        *args: Extra CLI arguments.

    Returns:
        Completed subprocess result.
    """
    fixture_path = tmp_path / "recovery.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "recover-qq",
            "--fixture",
            str(fixture_path),
            "--confirm",
            "--json",
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def healthy_fixture() -> dict:
    """Return a deterministic healthy remote-runtime fixture."""
    return {
        "qdrant": {"reachable": True},
        "embedding": {"healthy": True, "dimension": 1024, "finite": True},
        "gateway": {"healthy": True, "ready": True},
        "astrbot": {
            "reachable": True,
            "platforms": [
                {
                    "type": "qq_napcat",
                    "status": "running",
                    "error_count": 0,
                }
            ],
        },
        "napcat": {"isLogin": True, "online": True, "accountPresent": True},
        "listeners": [
            {"port": 6099, "address": "127.0.0.1"},
            {"port": 6185, "address": "127.0.0.1"},
            {"port": 6333, "address": "127.0.0.1"},
            {"port": 8000, "address": "127.0.0.1"},
            {"port": 8090, "address": "127.0.0.1"},
        ],
    }


def test_full_verification_reports_a_healthy_runtime_without_sensitive_data(
    tmp_path,
) -> None:
    result = run_ops(tmp_path, healthy_fixture())

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert {check["id"] for check in payload["checks"]} == {
        "qdrant",
        "embedding",
        "gateway_health",
        "gateway_ready",
        "astrbot",
        "onebot_adapter",
        "qq_upstream",
        "listener_safety",
    }
    assert "token" not in result.stdout.lower()
    assert "account" not in result.stdout.lower()


def test_live_full_verification_checks_every_runtime_boundary(tmp_path) -> None:
    """The production path must exercise real HTTP boundaries, not fixtures."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = {"status": "ok"}
            if self.path == "/qdrant/collections":
                payload = {"result": {"collections": []}}
            elif self.path == "/embedding/health":
                payload = {"status": "ready"}
            elif self.path in {"/gateway/healthz", "/gateway/readyz"}:
                payload = {"status": "ok"}
            elif self.path == "/astr/api/v1/bots/stats":
                payload = {
                    "status": "ok",
                    "data": {
                        "platforms": [
                            {
                                "type": "qq_napcat",
                                "status": "running",
                                "error_count": 0,
                            }
                        ]
                    },
                }
            else:
                self.send_error(404)
                return
            self._send(payload)

        def do_POST(self):
            if self.path == "/embedding/v1/embeddings":
                payload = {"data": [{"embedding": [0.0] * 1024}]}
            elif self.path == "/astr/api/v1/auth/login":
                payload = {"status": "ok", "data": {"token": "astr-secret"}}
            elif self.path == "/nap/api/auth/login":
                payload = {"code": 0, "data": {"Credential": "nap-secret"}}
            elif self.path == "/nap/api/QQLogin/CheckLoginStatus":
                payload = {
                    "code": 0,
                    "data": {
                        "isLogin": True,
                        "online": True,
                        "account": {"uin": "redacted"},
                    },
                }
            else:
                self.send_error(404)
                return
            self._send(payload)

        def _send(self, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config_dir = tmp_path / "napcat"
    config_dir.mkdir()
    (config_dir / "webui.json").write_text(
        json.dumps({"token": "webui-secret"}),
        encoding="utf-8",
    )
    port = server.server_address[1]
    env = {
        **os.environ,
        "QDRANT_HOST_URL": f"http://127.0.0.1:{port}/qdrant",
        "QDRANT_API_KEY": "qdrant-secret",
        "EMBEDDING_BASE_URL": f"http://127.0.0.1:{port}/embedding/v1",
        "EMBEDDING_HEALTH_URL": f"http://127.0.0.1:{port}/embedding/health",
        "EMBEDDING_API_KEY": "embedding-secret",
        "EMBEDDING_DIMENSION": "1024",
        "AGENT_GATEWAY_HOST_URL": f"http://127.0.0.1:{port}/gateway",
        "ASTRBOT_DASHBOARD_URL": f"http://127.0.0.1:{port}/astr/api/v1",
        "ASTRBOT_DASHBOARD_USERNAME": "operator",
        "ASTRBOT_DASHBOARD_PASSWORD": "dashboard-secret",
        "NAPCAT_WEBUI_URL": f"http://127.0.0.1:{port}/nap/api",
        "NAPCAT_CONFIG_DIR": str(config_dir),
    }
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "verify", "--json"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "ok"
    for secret in (
        "qdrant-secret",
        "embedding-secret",
        "dashboard-secret",
        "webui-secret",
        "astr-secret",
        "nap-secret",
        "redacted",
    ):
        assert secret not in result.stdout


def test_qq_ghost_online_state_requires_login_recovery(tmp_path) -> None:
    fixture = healthy_fixture()
    fixture["napcat"]["online"] = False

    result = run_ops(tmp_path, fixture)

    assert result.returncode == 20
    payload = json.loads(result.stdout)
    failed = {check["id"]: check["reason_code"] for check in payload["checks"]}
    assert failed["onebot_adapter"] == "ok"
    assert failed["qq_upstream"] == "qq_login_required"
    assert payload["recovery_action"] == "recover_qq"


def test_management_listeners_allow_tailscale_but_never_publish_onebot(
    tmp_path,
) -> None:
    fixture = healthy_fixture()
    fixture["listeners"] = [
        {"port": 6099, "address": "127.0.0.1"},
        {"port": 6185, "address": "100.66.104.25"},
        {"port": 6333, "address": "127.0.0.1"},
        {"port": 8000, "address": "127.0.0.1"},
        {"port": 8090, "address": "127.0.0.1"},
        {"port": 16099, "address": "100.66.104.25"},
    ]

    safe = run_ops(tmp_path, fixture)

    assert safe.returncode == 0, safe.stderr

    fixture["listeners"].append({"port": 6199, "address": "127.0.0.1"})
    unsafe = run_ops(tmp_path, fixture)

    assert unsafe.returncode == 22
    assert json.loads(unsafe.stdout)["recovery_action"] == "restrict_listener"


def test_recovery_changes_only_napcat_and_reverifies_the_full_chain(tmp_path) -> None:
    before = {
        service: {"id": service, "started_at": "before"}
        for service in (
            "astrbot",
            "napcat",
            "astrbot-agent-gateway",
            "astrbot-qdrant",
            "astrbot-embedding",
        )
    }
    after = json.loads(json.dumps(before))
    after["napcat"] = {"id": "napcat-new", "started_at": "after"}

    result = run_recovery(
        tmp_path,
        {
            "containers_before": before,
            "containers_after": after,
            "verification": healthy_fixture(),
        },
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["changed_services"] == ["napcat"]
    assert payload["verification"]["status"] == "ok"


def test_temporary_proxy_refuses_non_tailscale_bind_addresses() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "proxy",
            "--bind",
            "0.0.0.0",
            "--validate-only",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 22
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "failed",
        "reason_code": "unsafe_proxy_bind",
        "recovery_action": "use_tailscale_address",
    }


def test_coogen_fixture_replays_all_public_recovery_outcomes() -> None:
    """The publication bundle must be deterministic and require no secrets."""
    result = subprocess.run(
        [sys.executable, str(COOGEN_FIXTURE / "run_workflow.py")],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "ok",
        "scenarios": {
            "healthy_deployment": "passed",
            "ghost_online_recovery": "passed",
            "qr_required_safe_halt": "passed",
        },
    }
    lowered = result.stdout.lower()
    assert "token" not in lowered
    assert "password" not in lowered
    assert "qq_id" not in lowered
