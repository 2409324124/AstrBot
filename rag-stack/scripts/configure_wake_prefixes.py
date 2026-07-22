#!/usr/bin/env python3
"""Add or restore managed AstrBot wake-prefix aliases."""

import argparse
import copy
import json
import os
from pathlib import Path

import httpx

DEFAULT_ALIASES = ("东云bot", "东云Bot", "东云BOT")


def add_wake_prefixes(config: dict, aliases: list[str]) -> dict:
    """Append missing aliases and capture the original setting.

    Args:
        config: Writable AstrBot system configuration.
        aliases: Wake prefixes to append in order.

    Returns:
        Minimal state needed to restore the original setting.
    """
    present = "wake_prefix" in config
    previous = list(config.get("wake_prefix", []))
    updated = list(previous)
    for alias in aliases:
        if alias and alias not in updated:
            updated.append(alias)
    config["wake_prefix"] = updated
    return {"present": present, "value": previous}


def restore_wake_prefixes(config: dict, state: dict) -> None:
    """Restore the wake-prefix setting captured before deployment.

    Args:
        config: Writable AstrBot system configuration.
        state: State returned by :func:`add_wake_prefixes`.
    """
    if state.get("present"):
        config["wake_prefix"] = list(state.get("value", []))
    else:
        config.pop("wake_prefix", None)


def require_ok(response: httpx.Response) -> dict:
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") not in {"ok", None}:
        raise RuntimeError(str(payload.get("message", payload)))
    return payload


def authenticated_client(base_url: str) -> httpx.Client:
    client = httpx.Client(timeout=60)
    payload = require_ok(
        client.post(
            f"{base_url}/auth/login",
            json={
                "username": os.environ["ASTRBOT_DASHBOARD_USERNAME"],
                "password": os.environ["ASTRBOT_DASHBOARD_PASSWORD"],
            },
        )
    )
    token = payload.get("data", {}).get("token")
    if not token:
        raise RuntimeError("AstrBot login did not return a token")
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def get_system_config(client: httpx.Client, base_url: str) -> dict:
    payload = require_ok(client.get(f"{base_url}/system-config"))
    config = payload.get("data", {}).get("config")
    if not isinstance(config, dict):
        raise RuntimeError("AstrBot did not return a writable system config")
    return config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("apply", "restore"))
    parser.add_argument("--alias", action="append", dest="aliases")
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(__file__).parents[1] / "runtime" / "wake-prefix-backup.json",
    )
    args = parser.parse_args()
    aliases = args.aliases or list(DEFAULT_ALIASES)
    base_url = os.environ.get(
        "ASTRBOT_DASHBOARD_URL", "http://127.0.0.1:6185/api/v1"
    ).rstrip("/")

    client = authenticated_client(base_url)
    try:
        current = get_system_config(client, base_url)
        updated = copy.deepcopy(current)
        if args.action == "apply":
            state = add_wake_prefixes(updated, aliases)
            changed = updated != current
            if changed:
                args.state_file.parent.mkdir(parents=True, exist_ok=True)
                args.state_file.write_text(
                    json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        else:
            state = json.loads(args.state_file.read_text(encoding="utf-8"))
            restore_wake_prefixes(updated, state)
            changed = updated != current
        if changed:
            require_ok(client.put(f"{base_url}/system-config", json=updated))
    finally:
        client.close()

    print(json.dumps({"status": "ok", "action": args.action, "changed": changed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
