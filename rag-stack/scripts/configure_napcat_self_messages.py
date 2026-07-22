#!/usr/bin/env python3
"""Enable self-message reports on NapCat's active AstrBot WS client."""

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx


def enable_self_messages(config: dict, *, adapter_name: str) -> bool:
    """Enable reports on exactly one active named WebSocket client.

    Args:
        config: Parsed NapCat OneBot configuration.
        adapter_name: Name of the active reverse WebSocket client.

    Returns:
        Whether the configuration changed.

    Raises:
        RuntimeError: No unique enabled client matches ``adapter_name``.
    """
    clients = config.get("network", {}).get("websocketClients", [])
    matches = [
        client
        for client in clients
        if client.get("enable") is True and client.get("name") == adapter_name
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one enabled websocket client named {adapter_name!r}"
        )
    changed = config.pop("reportSelfMessage", None) is not None
    if matches[0].get("reportSelfMessage") is not True:
        matches[0]["reportSelfMessage"] = True
        changed = True
    return changed


def require_success(response: httpx.Response) -> dict:
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(str(payload.get("message", "NapCat WebUI request failed")))
    return payload


def load_webui_token(config_dir: Path) -> str:
    config = json.loads((config_dir / "webui.json").read_text(encoding="utf-8-sig"))
    token = str(config.get("token", "")).strip()
    if not token:
        raise RuntimeError("NapCat WebUI token is empty")
    return token


def save_private_backup(config: dict, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = backup_dir / f"onebot11-before-self-messages-{stamp}.json"
    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--adapter-name", default="astrbot")
    parser.add_argument("--base-url", default="http://127.0.0.1:6099/api")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path(__file__).parents[1] / "runtime" / "napcat-backups",
    )
    args = parser.parse_args()

    token = load_webui_token(args.config_dir)
    token_hash = hashlib.sha256(f"{token}.napcat".encode()).hexdigest()
    base_url = args.base_url.rstrip("/")

    with httpx.Client(timeout=60) as client:
        login = require_success(
            client.post(f"{base_url}/auth/login", json={"hash": token_hash})
        )
        credential = login.get("data", {}).get("Credential")
        if not credential:
            raise RuntimeError("NapCat WebUI login returned no credential")
        client.headers["Authorization"] = f"Bearer {credential}"

        payload = require_success(client.post(f"{base_url}/OB11Config/GetConfig"))
        config = payload.get("data")
        if not isinstance(config, dict):
            raise RuntimeError("NapCat WebUI returned no OneBot config")
        backup_path = save_private_backup(config, args.backup_dir)
        changed = enable_self_messages(config, adapter_name=args.adapter_name)
        if changed:
            require_success(
                client.post(
                    f"{base_url}/OB11Config/SetConfig",
                    json={"config": json.dumps(config, ensure_ascii=False)},
                )
            )

        verified_payload = require_success(
            client.post(f"{base_url}/OB11Config/GetConfig")
        )
        verified = verified_payload.get("data")
        if not isinstance(verified, dict):
            raise RuntimeError("NapCat verification returned no OneBot config")
        clients = verified.get("network", {}).get("websocketClients", [])
        selected_clients = [
            client
            for client in clients
            if client.get("enable") is True and client.get("name") == args.adapter_name
        ]
        if len(selected_clients) != 1:
            raise RuntimeError("NapCat verification could not find the active client")
        selected = selected_clients[0]
        if selected.get("reportSelfMessage") is not True:
            raise RuntimeError("NapCat did not persist reportSelfMessage=true")

    print(
        json.dumps(
            {
                "status": "ok",
                "changed": changed,
                "adapter": args.adapter_name,
                "backup": str(backup_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
