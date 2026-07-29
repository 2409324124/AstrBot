#!/usr/bin/env python3
"""Verify and recover the AstrBot, NapCat, and local RAG runtime."""

import argparse
import asyncio
import hashlib
import ipaddress
import json
import math
import os
import subprocess
import time
from pathlib import Path

import httpx

EXIT_INFRA_UNHEALTHY = 10
EXIT_QQ_LOGIN_REQUIRED = 20
EXIT_ADAPTER_DISCONNECTED = 21
EXIT_UNSAFE_LISTENER = 22


def evaluate_state(fixture: dict, mode: str) -> tuple[int, dict]:
    """Evaluate sanitized observations from live services or a fixture.

    Args:
        fixture: Sanitized observable service state.
        mode: Verification subset: core, messaging, or full.

    Returns:
        Exit code and redacted verification report.
    """
    checks = []

    def add(check_id: str, passed: bool, reason_code: str) -> None:
        checks.append(
            {
                "id": check_id,
                "status": "pass" if passed else "fail",
                "latency_ms": 0,
                "reason_code": "ok" if passed else reason_code,
            }
        )

    exit_code = 0
    recovery_action = "none"
    if mode in {"core", "full"}:
        qdrant_ok = fixture.get("qdrant", {}).get("reachable") is True
        add("qdrant", qdrant_ok, "qdrant_unreachable")
        embedding = fixture.get("embedding", {})
        embedding_ok = (
            embedding.get("healthy") is True
            and embedding.get("dimension") == 1024
            and embedding.get("finite") is True
        )
        add("embedding", embedding_ok, "embedding_invalid")
        gateway = fixture.get("gateway", {})
        add("gateway_health", gateway.get("healthy") is True, "gateway_unhealthy")
        add("gateway_ready", gateway.get("ready") is True, "gateway_not_ready")
        if not all(check["status"] == "pass" for check in checks):
            exit_code = EXIT_INFRA_UNHEALTHY
            recovery_action = "inspect_infrastructure"

    if mode in {"messaging", "full"}:
        astrbot = fixture.get("astrbot", {})
        astrbot_ok = astrbot.get("reachable") is True
        add("astrbot", astrbot_ok, "astrbot_unreachable")
        platforms = astrbot.get("platforms", [])
        adapters = [
            platform for platform in platforms if platform.get("type") == "qq_napcat"
        ]
        adapter_ok = (
            len(adapters) == 1
            and adapters[0].get("status") == "running"
            and adapters[0].get("error_count") == 0
        )
        add("onebot_adapter", adapter_ok, "adapter_disconnected")
        napcat = fixture.get("napcat", {})
        qq_ok = (
            napcat.get("isLogin") is True
            and napcat.get("online") is True
            and napcat.get("accountPresent") is True
        )
        add("qq_upstream", qq_ok, "qq_login_required")

        listeners_ok = True
        loopback_only_ports = {6099, 6333, 8000, 8090}
        tailscale_network = ipaddress.ip_network("100.64.0.0/10")
        for listener in fixture.get("listeners", []):
            port = listener.get("port")
            address_text = str(listener.get("address", ""))
            try:
                address = ipaddress.ip_address(address_text.split("%", 1)[0])
            except ValueError:
                address = None
            if port == 6199:
                listeners_ok = False
            elif port in loopback_only_ports and not (
                address is not None and address.is_loopback
            ):
                listeners_ok = False
            elif port == 6185 and not (
                address is not None
                and (address.is_loopback or address in tailscale_network)
            ):
                listeners_ok = False
            elif port == 16099 and not (
                address is not None and address in tailscale_network
            ):
                listeners_ok = False
        add("listener_safety", listeners_ok, "unsafe_listener")

        if not listeners_ok:
            exit_code = EXIT_UNSAFE_LISTENER
            recovery_action = "restrict_listener"
        elif not qq_ok:
            exit_code = EXIT_QQ_LOGIN_REQUIRED
            recovery_action = "recover_qq"
        elif not astrbot_ok or not adapter_ok:
            exit_code = EXIT_ADAPTER_DISCONNECTED
            recovery_action = "inspect_adapter"

    report = {
        "status": "ok" if exit_code == 0 else "failed",
        "checks": checks,
        "recovery_action": recovery_action,
    }
    return exit_code, report


def verify_fixture(fixture_path: Path, mode: str) -> tuple[int, dict]:
    """Evaluate a deterministic, secret-free runtime fixture.

    Args:
        fixture_path: JSON file describing observable service state.
        mode: Verification subset: core, messaging, or full.

    Returns:
        Exit code and redacted verification report.
    """
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    return evaluate_state(fixture, mode)


def verify_live(mode: str) -> tuple[int, dict]:
    """Collect live service observations and evaluate the runtime.

    Args:
        mode: Verification subset: core, messaging, or full.

    Returns:
        Exit code and redacted verification report.
    """
    state: dict = {}
    timeout = float(os.environ.get("ASTRBOT_OPS_TIMEOUT", "10"))
    with httpx.Client(timeout=timeout) as client:
        if mode in {"core", "full"}:
            qdrant_url = os.environ.get(
                "QDRANT_HOST_URL", "http://127.0.0.1:6333"
            ).rstrip("/")
            try:
                response = client.get(
                    f"{qdrant_url}/collections",
                    headers={"api-key": os.environ["QDRANT_API_KEY"]},
                )
                response.raise_for_status()
                state["qdrant"] = {"reachable": True}
            except (httpx.HTTPError, KeyError, ValueError):
                state["qdrant"] = {"reachable": False}

            embedding_base = os.environ.get(
                "EMBEDDING_BASE_URL", "http://127.0.0.1:8000/v1"
            ).rstrip("/")
            embedding_health = os.environ.get(
                "EMBEDDING_HEALTH_URL", "http://127.0.0.1:8000/health"
            )
            embedding_state = {
                "healthy": False,
                "dimension": 0,
                "finite": False,
            }
            try:
                headers = {"Authorization": f"Bearer {os.environ['EMBEDDING_API_KEY']}"}
                response = client.get(embedding_health, headers=headers)
                response.raise_for_status()
                response = client.post(
                    f"{embedding_base}/embeddings",
                    headers=headers,
                    json={
                        "model": os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3"),
                        "input": ["runtime verification"],
                    },
                )
                response.raise_for_status()
                vector = response.json()["data"][0]["embedding"]
                embedding_state = {
                    "healthy": True,
                    "dimension": len(vector),
                    "finite": all(math.isfinite(value) for value in vector),
                }
            except (httpx.HTTPError, KeyError, TypeError, ValueError):
                pass
            state["embedding"] = embedding_state

            gateway_url = os.environ.get(
                "AGENT_GATEWAY_HOST_URL", "http://127.0.0.1:8090"
            ).rstrip("/")
            gateway_state = {"healthy": False, "ready": False}
            try:
                response = client.get(f"{gateway_url}/healthz")
                response.raise_for_status()
                gateway_state["healthy"] = True
                response = client.get(f"{gateway_url}/readyz")
                response.raise_for_status()
                gateway_state["ready"] = True
            except httpx.HTTPError:
                pass
            state["gateway"] = gateway_state

        if mode in {"messaging", "full"}:
            astrbot_url = os.environ.get(
                "ASTRBOT_DASHBOARD_URL", "http://127.0.0.1:6185/api/v1"
            ).rstrip("/")
            astrbot_state = {"reachable": False, "platforms": []}
            try:
                response = client.post(
                    f"{astrbot_url}/auth/login",
                    json={
                        "username": os.environ["ASTRBOT_DASHBOARD_USERNAME"],
                        "password": os.environ["ASTRBOT_DASHBOARD_PASSWORD"],
                    },
                )
                response.raise_for_status()
                credential = response.json()["data"]["token"]
                response = client.get(
                    f"{astrbot_url}/bots/stats",
                    headers={"Authorization": f"Bearer {credential}"},
                )
                response.raise_for_status()
                astrbot_state = {
                    "reachable": True,
                    "platforms": response.json().get("data", {}).get("platforms", []),
                }
            except (httpx.HTTPError, KeyError, TypeError, ValueError):
                pass
            state["astrbot"] = astrbot_state

            napcat_state = {
                "isLogin": False,
                "online": False,
                "accountPresent": False,
            }
            try:
                config_dir = Path(os.environ["NAPCAT_CONFIG_DIR"])
                config = json.loads(
                    (config_dir / "webui.json").read_text(encoding="utf-8-sig")
                )
                webui_secret = str(config["token"])
                derived = hashlib.sha256(f"{webui_secret}.napcat".encode()).hexdigest()
                napcat_url = os.environ.get(
                    "NAPCAT_WEBUI_URL", "http://127.0.0.1:6099/api"
                ).rstrip("/")
                response = client.post(
                    f"{napcat_url}/auth/login", json={"hash": derived}
                )
                response.raise_for_status()
                credential = response.json()["data"]["Credential"]
                response = client.post(
                    f"{napcat_url}/QQLogin/CheckLoginStatus",
                    headers={"Authorization": f"Bearer {credential}"},
                )
                response.raise_for_status()
                data = response.json().get("data", {})
                napcat_state = {
                    "isLogin": data.get("isLogin") is True,
                    "online": data.get("online") is True,
                    "accountPresent": any(
                        bool(data.get(key))
                        for key in ("account", "qqInfo", "loginInfo")
                    ),
                }
            except (httpx.HTTPError, KeyError, TypeError, ValueError, OSError):
                pass
            state["napcat"] = napcat_state

            listeners = []
            try:
                result = subprocess.run(
                    ["ss", "-H", "-ltn"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                for line in result.stdout.splitlines():
                    fields = line.split()
                    if len(fields) < 4:
                        continue
                    endpoint = fields[3]
                    address, separator, port_text = endpoint.rpartition(":")
                    if separator and port_text.isdigit():
                        listeners.append(
                            {
                                "port": int(port_text),
                                "address": address.strip("[]"),
                            }
                        )
            except (OSError, subprocess.SubprocessError):
                listeners = []
            state["listeners"] = listeners

    return evaluate_state(state, mode)


def recover_fixture(fixture_path: Path) -> tuple[int, dict]:
    """Evaluate a deterministic minimal-restart recovery fixture.

    Args:
        fixture_path: JSON file containing before/after runtime observations.

    Returns:
        Exit code and redacted recovery report.
    """
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    before = fixture.get("containers_before", {})
    after = fixture.get("containers_after", {})
    changed = sorted(
        service
        for service in set(before) | set(after)
        if before.get(service) != after.get(service)
    )
    unexpected = [service for service in changed if service != "napcat"]
    if unexpected:
        return EXIT_INFRA_UNHEALTHY, {
            "status": "failed",
            "changed_services": changed,
            "reason_code": "unexpected_service_change",
            "recovery_action": "inspect_infrastructure",
        }

    verify_code, verification = evaluate_state(fixture.get("verification", {}), "full")
    return verify_code, {
        "status": "ok" if verify_code == 0 else "failed",
        "changed_services": changed,
        "reason_code": "ok" if verify_code == 0 else "verification_failed",
        "recovery_action": verification["recovery_action"],
        "verification": verification,
    }


def recover_live(timeout_seconds: int) -> tuple[int, dict]:
    """Restart only NapCat and verify that the complete chain recovers.

    Args:
        timeout_seconds: Maximum number of seconds to wait for QQ login.

    Returns:
        Exit code and redacted recovery report.

    Raises:
        RuntimeError: Docker inspection or the scoped restart fails.
    """
    services = (
        "astrbot",
        "napcat",
        "astrbot-agent-gateway",
        "astrbot-qdrant",
        "astrbot-embedding",
    )
    configured = os.environ.get("ASTRBOT_DOCKER_BIN", "").strip()
    if configured:
        docker = [configured]
    else:
        probe = subprocess.run(
            ["docker", "info"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        docker = ["docker"] if probe.returncode == 0 else ["sudo", "docker"]

    def snapshot() -> dict:
        result = subprocess.run(
            [
                *docker,
                "inspect",
                "--format",
                "{{.Name}}|{{.Id}}|{{.State.StartedAt}}",
                *services,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError("container inspection failed")
        observed = {}
        for line in result.stdout.splitlines():
            name, separator, rest = line.partition("|")
            container_id, separator_two, started_at = rest.partition("|")
            if not separator or not separator_two:
                raise RuntimeError("container inspection returned invalid data")
            observed[name.lstrip("/")] = {
                "id": container_id,
                "started_at": started_at,
            }
        if set(observed) != set(services):
            raise RuntimeError("container inspection returned an incomplete set")
        return observed

    before = snapshot()
    stack_root = Path(__file__).parents[1]
    env_file = os.environ.get("RAG_ENV_FILE", str(stack_root / ".env"))
    compose_file = os.environ.get(
        "ASTRBOT_COMPOSE_FILE", str(stack_root / "../../compose.yml")
    )
    restart = subprocess.run(
        [
            *docker,
            "compose",
            "--env-file",
            env_file,
            "-f",
            compose_file,
            "-f",
            str(stack_root / "astrbot.override.yml"),
            "restart",
            "napcat",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if restart.returncode != 0:
        raise RuntimeError("scoped NapCat restart failed")

    deadline = time.monotonic() + timeout_seconds
    verify_code = EXIT_QQ_LOGIN_REQUIRED
    verification = {
        "status": "failed",
        "checks": [],
        "recovery_action": "recover_qq",
    }
    while True:
        verify_code, verification = verify_live("full")
        if verify_code == 0 or time.monotonic() >= deadline:
            break
        time.sleep(min(2, max(0, deadline - time.monotonic())))

    after = snapshot()
    changed = sorted(
        service for service in services if before[service] != after[service]
    )
    if changed != ["napcat"]:
        return EXIT_INFRA_UNHEALTHY, {
            "status": "failed",
            "changed_services": changed,
            "reason_code": "unexpected_service_change",
            "recovery_action": "inspect_infrastructure",
        }
    return verify_code, {
        "status": "ok" if verify_code == 0 else "failed",
        "changed_services": changed,
        "reason_code": "ok" if verify_code == 0 else "verification_failed",
        "recovery_action": verification["recovery_action"],
        "verification": verification,
    }


def validate_proxy_endpoints(bind: str, target_host: str) -> bool:
    """Validate that the proxy stays on Tailscale and targets loopback.

    Args:
        bind: Listener address.
        target_host: Forward target address.

    Returns:
        Whether the endpoints satisfy the exposure policy.
    """
    try:
        bind_address = ipaddress.ip_address(bind.split("%", 1)[0])
        target_address = ipaddress.ip_address(target_host.split("%", 1)[0])
    except ValueError:
        return False
    return (
        bind_address in ipaddress.ip_network("100.64.0.0/10")
        and target_address.is_loopback
    )


async def run_temporary_proxy(
    bind: str,
    port: int,
    target_host: str,
    target_port: int,
    ttl_seconds: int,
) -> None:
    """Run a foreground TCP proxy that closes after a fixed TTL.

    Args:
        bind: Tailscale listener address.
        port: Tailscale listener port.
        target_host: Loopback target address.
        target_port: Loopback target port.
        ttl_seconds: Maximum lifetime in seconds.
    """

    async def forward(
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        try:
            target_reader, target_writer = await asyncio.open_connection(
                target_host, target_port
            )
        except OSError:
            client_writer.close()
            await client_writer.wait_closed()
            return

        async def pump(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            while data := await reader.read(65536):
                writer.write(data)
                await writer.drain()

        tasks = {
            asyncio.create_task(pump(client_reader, target_writer)),
            asyncio.create_task(pump(target_reader, client_writer)),
        }
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*done, *pending, return_exceptions=True)
        target_writer.close()
        client_writer.close()
        await asyncio.gather(
            target_writer.wait_closed(),
            client_writer.wait_closed(),
            return_exceptions=True,
        )

    server = await asyncio.start_server(forward, bind, port)
    async with server:
        await asyncio.sleep(ttl_seconds)


def main() -> int:
    """Run the operations command.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument(
        "--mode",
        choices=("core", "messaging", "full"),
        default="full",
    )
    verify_parser.add_argument("--fixture", type=Path)
    verify_parser.add_argument("--json", action="store_true")
    recover_parser = subparsers.add_parser("recover-qq")
    recover_parser.add_argument("--fixture", type=Path)
    recover_parser.add_argument("--confirm", action="store_true")
    recover_parser.add_argument("--json", action="store_true")
    recover_parser.add_argument("--timeout", type=int, default=60)
    proxy_parser = subparsers.add_parser("proxy")
    proxy_parser.add_argument("--bind", required=True)
    proxy_parser.add_argument("--port", type=int, default=16099)
    proxy_parser.add_argument("--target-host", default="127.0.0.1")
    proxy_parser.add_argument("--target-port", type=int, default=6099)
    proxy_parser.add_argument("--ttl", type=int, default=900)
    proxy_parser.add_argument("--validate-only", action="store_true")
    proxy_parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.command == "proxy":
        if not validate_proxy_endpoints(args.bind, args.target_host):
            report = {
                "status": "failed",
                "reason_code": "unsafe_proxy_bind",
                "recovery_action": "use_tailscale_address",
            }
            if args.json:
                print(json.dumps(report, separators=(",", ":")))
            else:
                print("status=failed action=use_tailscale_address")
            return EXIT_UNSAFE_LISTENER
        report = {
            "status": "ok",
            "url": f"http://{args.bind}:{args.port}/webui",
            "ttl_seconds": args.ttl,
        }
        if args.json:
            print(json.dumps(report, separators=(",", ":")), flush=True)
        else:
            print(
                f"Temporary NapCat UI: {report['url']} (TTL {args.ttl}s)",
                flush=True,
            )
        if not args.validate_only:
            try:
                asyncio.run(
                    run_temporary_proxy(
                        args.bind,
                        args.port,
                        args.target_host,
                        args.target_port,
                        args.ttl,
                    )
                )
            except OSError:
                return EXIT_INFRA_UNHEALTHY
        return 0
    if args.command == "verify" and args.fixture:
        exit_code, report = verify_fixture(args.fixture, args.mode)
    elif args.command == "verify":
        exit_code, report = verify_live(args.mode)
    elif not args.confirm:
        parser.error("recover-qq requires --confirm")
    elif args.fixture:
        exit_code, report = recover_fixture(args.fixture)
    else:
        try:
            exit_code, report = recover_live(args.timeout)
        except RuntimeError:
            exit_code, report = (
                EXIT_INFRA_UNHEALTHY,
                {
                    "status": "failed",
                    "changed_services": [],
                    "reason_code": "recovery_command_failed",
                    "recovery_action": "inspect_infrastructure",
                },
            )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    else:
        print(f"status={report['status']} action={report['recovery_action']}")
        for check in report["checks"]:
            print(f"{check['id']}: {check['status']} ({check['reason_code']})")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
