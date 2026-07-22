#!/usr/bin/env python3
"""Enable or restore Exa web search without storing the API key in AstrBot."""

import argparse
import copy
import json
import os
from pathlib import Path

import httpx

WEB_SEARCH_SETTINGS = (
    "web_search",
    "websearch_provider",
    "web_search_link",
    "verified_factual_reply_policy",
)


def require_ok(response: httpx.Response) -> dict:
    """Return a dashboard payload or fail without exposing its credentials."""
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") not in {"ok", None}:
        raise RuntimeError(str(payload.get("message", payload)))
    return payload


def save_previous_settings(provider_settings: dict) -> dict:
    """Record only mutable search switches; API key fields are never persisted."""
    return {
        setting: {
            "present": setting in provider_settings,
            "value": provider_settings.get(setting),
        }
        for setting in WEB_SEARCH_SETTINGS
    }


def enable_exa_web_search(config: dict) -> dict:
    """Enable the Exa tool set and return a minimal restore state."""
    provider_settings = config.setdefault("provider_settings", {})
    state = save_previous_settings(provider_settings)
    provider_settings.update(
        {
            "web_search": True,
            "websearch_provider": "exa",
            "web_search_link": True,
            "verified_factual_reply_policy": True,
        },
    )
    return state


def restore_web_search_settings(config: dict, state: dict) -> None:
    """Restore only the web-search and reply-policy switches saved by this script."""
    provider_settings = config.setdefault("provider_settings", {})
    for setting in WEB_SEARCH_SETTINGS:
        previous = state.get(setting, {})
        if previous.get("present"):
            provider_settings[setting] = previous.get("value")
        else:
            provider_settings.pop(setting, None)


def authenticated_client(base_url: str) -> httpx.Client:
    """Create a dashboard client using credentials passed through the env file."""
    client = httpx.Client(timeout=60)
    payload = require_ok(
        client.post(
            f"{base_url}/auth/login",
            json={
                "username": os.environ["ASTRBOT_DASHBOARD_USERNAME"],
                "password": os.environ["ASTRBOT_DASHBOARD_PASSWORD"],
            },
        ),
    )
    token = payload.get("data", {}).get("token")
    if not token:
        raise RuntimeError("AstrBot login did not return a token")
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def get_system_config(client: httpx.Client, base_url: str) -> dict:
    """Fetch the full default profile required by AstrBot's config API."""
    payload = require_ok(client.get(f"{base_url}/system-config"))
    config = payload.get("data", {}).get("config")
    if not isinstance(config, dict):
        raise RuntimeError("AstrBot did not return a writable system config")
    return config


def update_system_config(client: httpx.Client, base_url: str, config: dict) -> None:
    """Replace the validated default profile through the dashboard API."""
    require_ok(client.put(f"{base_url}/system-config", json=config))


def main() -> int:
    """Enable Exa only when its untracked container secret is present."""
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("apply", "restore"))
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(__file__).parents[1] / "runtime" / "exa-web-search-backup.json",
    )
    args = parser.parse_args()

    if (
        args.action == "apply"
        and not os.environ.get("ASTRBOT_WEBSEARCH_EXA_KEY", "").strip()
    ):
        raise RuntimeError(
            "ASTRBOT_WEBSEARCH_EXA_KEY is empty; add it to the ignored rag-stack/.env first.",
        )

    base_url = os.environ.get(
        "ASTRBOT_DASHBOARD_URL", "http://127.0.0.1:6185/api/v1"
    ).rstrip("/")
    client = authenticated_client(base_url)
    try:
        config = get_system_config(client, base_url)
        if args.action == "apply":
            next_config = copy.deepcopy(config)
            state = enable_exa_web_search(next_config)
            args.state_file.parent.mkdir(parents=True, exist_ok=True)
            args.state_file.write_text(
                json.dumps({"provider_settings": state}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            update_system_config(client, base_url, next_config)
        else:
            state = json.loads(args.state_file.read_text(encoding="utf-8"))
            next_config = copy.deepcopy(config)
            restore_web_search_settings(
                next_config,
                state.get("provider_settings", {}),
            )
            update_system_config(client, base_url, next_config)
    finally:
        client.close()
    print(json.dumps({"status": "ok", "action": args.action}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
