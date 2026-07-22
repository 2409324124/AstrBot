#!/usr/bin/env python3
"""Create the local embedding provider and switch knowledge-base providers."""

import argparse
import json
import os
from pathlib import Path

import httpx


def require_ok(response: httpx.Response) -> dict:
    """Validate an AstrBot dashboard API response.

    Args:
        response: Dashboard response.

    Returns:
        Parsed response payload.

    Raises:
        RuntimeError: If HTTP or AstrBot status indicates failure.
    """
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") not in {"ok", None}:
        raise RuntimeError(str(payload.get("message", payload)))
    return payload


def main() -> int:
    """Apply or restore embedding provider assignments.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("apply", "restore"))
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(__file__).parents[1] / "runtime" / "provider-backup.json",
    )
    args = parser.parse_args()
    base_url = os.environ.get(
        "ASTRBOT_DASHBOARD_URL",
        "http://127.0.0.1:6185/api/v1",
    ).rstrip("/")
    provider_id = os.environ.get(
        "ASTRBOT_EMBEDDING_PROVIDER_ID",
        "local_bge_m3",
    )
    client = httpx.Client(timeout=60)
    login = require_ok(
        client.post(
            f"{base_url}/auth/login",
            json={
                "username": os.environ["ASTRBOT_DASHBOARD_USERNAME"],
                "password": os.environ["ASTRBOT_DASHBOARD_PASSWORD"],
            },
        ),
    )
    token = login.get("data", {}).get("token")
    if not token:
        raise RuntimeError("AstrBot login did not return a token")
    client.headers["Authorization"] = f"Bearer {token}"

    if args.action == "apply":
        provider_config = {
            "id": provider_id,
            "type": "openai_embedding",
            "provider": "openai",
            "provider_type": "embedding",
            "enable": True,
            "embedding_api_key": os.environ["EMBEDDING_API_KEY"],
            "embedding_api_base": os.environ.get(
                "EMBEDDING_DOCKER_BASE_URL",
                "http://embedding-server:8000/v1",
            ),
            "embedding_model": os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3"),
            "embedding_dimensions": int(
                os.environ.get("EMBEDDING_DIMENSION", "1024"),
            ),
            "timeout": 60,
            "proxy": "",
        }
        providers = require_ok(client.get(f"{base_url}/providers"))["data"]["providers"]
        existing_ids = {item.get("id") for item in providers if isinstance(item, dict)}
        if provider_id in existing_ids:
            require_ok(
                client.put(
                    f"{base_url}/providers/by-id",
                    json={"provider_id": provider_id, "config": provider_config},
                ),
            )
        else:
            require_ok(
                client.post(
                    f"{base_url}/providers",
                    json={"config": provider_config},
                ),
            )
        require_ok(client.post(f"{base_url}/providers/{provider_id}/test"))

        kbs = require_ok(
            client.get(
                f"{base_url}/knowledge-bases",
                params={"page": 1, "page_size": 1000},
            ),
        )["data"]["items"]
        state = {
            "provider_id": provider_id,
            "knowledge_bases": {
                kb["kb_id"]: kb.get("embedding_provider_id") for kb in kbs
            },
        }
        args.state_file.parent.mkdir(parents=True, exist_ok=True)
        args.state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for kb in kbs:
            require_ok(
                client.put(
                    f"{base_url}/knowledge-bases/{kb['kb_id']}",
                    json={"embedding_provider_id": provider_id},
                ),
            )
    else:
        state = json.loads(args.state_file.read_text(encoding="utf-8"))
        for kb_id, old_provider_id in state["knowledge_bases"].items():
            require_ok(
                client.put(
                    f"{base_url}/knowledge-bases/{kb_id}",
                    json={"embedding_provider_id": old_provider_id},
                ),
            )

    print(json.dumps({"status": "ok", "action": args.action}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
