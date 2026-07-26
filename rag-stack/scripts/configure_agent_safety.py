#!/usr/bin/env python3
"""Disable or restore AstrBot capabilities excluded from this deployment."""

import argparse
import copy
import json
import os
from pathlib import Path

import httpx


def disable_cron_tools(config: dict) -> dict:
    """Disable Agent cron tools and return their minimal restore state.

    Args:
        config: Writable AstrBot system configuration.

    Returns:
        Whether the setting existed and its previous value.
    """
    proactive = config.setdefault("provider_settings", {}).setdefault(
        "proactive_capability", {}
    )
    state = {
        "present": "add_cron_tools" in proactive,
        "value": proactive.get("add_cron_tools"),
    }
    proactive["add_cron_tools"] = False
    return state


def restore_cron_tools(config: dict, state: dict) -> None:
    """Restore only the cron-tool setting saved by this script.

    Args:
        config: Writable AstrBot system configuration.
        state: Restore state returned by ``disable_cron_tools``.
    """
    proactive = config.setdefault("provider_settings", {}).setdefault(
        "proactive_capability", {}
    )
    if state.get("present"):
        proactive["add_cron_tools"] = state.get("value")
    else:
        proactive.pop("add_cron_tools", None)


def require_ok(response: httpx.Response) -> dict:
    """Return an AstrBot dashboard response or raise a useful error."""
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") not in {"ok", None}:
        raise RuntimeError(str(payload.get("message", payload)))
    return payload


def main() -> int:
    """Apply a reversible system-config safety boundary."""
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("apply", "restore"))
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(__file__).parents[1] / "runtime" / "agent-safety-backup.json",
    )
    args = parser.parse_args()
    base_url = os.environ.get(
        "ASTRBOT_DASHBOARD_URL", "http://127.0.0.1:6185/api/v1"
    ).rstrip("/")
    client = httpx.Client(timeout=60)
    try:
        login = require_ok(
            client.post(
                f"{base_url}/auth/login",
                json={
                    "username": os.environ["ASTRBOT_DASHBOARD_USERNAME"],
                    "password": os.environ["ASTRBOT_DASHBOARD_PASSWORD"],
                },
            )
        )
        token = login.get("data", {}).get("token")
        if not token:
            raise RuntimeError("AstrBot login did not return a token")
        client.headers["Authorization"] = f"Bearer {token}"
        payload = require_ok(client.get(f"{base_url}/system-config"))
        config = payload.get("data", {}).get("config")
        if not isinstance(config, dict):
            raise RuntimeError("AstrBot did not return a writable system config")
        next_config = copy.deepcopy(config)
        if args.action == "apply":
            state = disable_cron_tools(next_config)
            args.state_file.parent.mkdir(parents=True, exist_ok=True)
            args.state_file.write_text(
                json.dumps({"add_cron_tools": state}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            saved = json.loads(args.state_file.read_text(encoding="utf-8"))
            restore_cron_tools(next_config, saved.get("add_cron_tools", {}))
        require_ok(client.put(f"{base_url}/system-config", json=next_config))
    finally:
        client.close()
    print(json.dumps({"status": "ok", "action": args.action}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
