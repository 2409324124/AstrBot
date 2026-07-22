#!/usr/bin/env python3
"""Apply or restore the research-oriented group persona through AstrBot's API."""

import argparse
import json
import os
from pathlib import Path

import httpx

GROUP_RESEARCH_PROMPT_MARKER = "<!-- astrbot-group-research-v1 -->"
GROUP_RESEARCH_PROMPT = f"""

{GROUP_RESEARCH_PROMPT_MARKER}
## 群聊技术与检索行为

普通闲聊可以简短自然；但技术问题、学习、工程、算法、历史事实或研究问题不受短回复限制。
遇到“为什么”“条件够不够”“怎么证明”“展开讲”“教一下”等追问，要继承最近的技术话题或被引用内容，说明机制、前提、步骤、复杂度/边界，并在合适时给一个反例或小例子；不要只复述一个算法名，也不要为了附和而跳过独立判断。
对时效性、争议性、冷门事实、论文/产品比较、需要来源或用户明确要求研究的问题，先调用网页检索工具；需要时继续读取来源正文。使用检索结果后，在 QQ 回复末尾给出 1–3 个真实来源链接。若证据不足，要明确说不确定和还缺什么证据。
用户使用 `/research 问题`、`/研究 问题` 或 `/检索 问题` 时，必须先完成外部检索再回答。
""".strip()


def require_ok(response: httpx.Response) -> dict:
    """Return an AstrBot dashboard response or raise a useful error."""
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") not in {"ok", None}:
        raise RuntimeError(str(payload.get("message", payload)))
    return payload


def compose_group_persona_prompt(existing_prompt: str) -> str:
    """Append the managed behavior once while preserving the user's persona."""
    if GROUP_RESEARCH_PROMPT_MARKER in existing_prompt:
        return existing_prompt
    return f"{existing_prompt.rstrip()}\n\n{GROUP_RESEARCH_PROMPT}\n"


def authenticated_client(base_url: str) -> httpx.Client:
    """Log into the local dashboard using credentials supplied via the env file."""
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


def get_persona(client: httpx.Client, base_url: str, persona_id: str) -> dict:
    """Fetch one persona and normalize the dashboard response shape."""
    payload = require_ok(
        client.get(f"{base_url}/personas/by-id", params={"persona_id": persona_id}),
    )
    persona = payload.get("data")
    if not isinstance(persona, dict):
        raise RuntimeError(f"Persona {persona_id!r} was not returned by AstrBot")
    return persona


def update_prompt(
    client: httpx.Client,
    base_url: str,
    persona_id: str,
    prompt: str,
) -> None:
    """Update only the prompt, leaving tools, dialogs, and folders untouched."""
    require_ok(
        client.put(
            f"{base_url}/personas/by-id",
            json={"persona_id": persona_id, "system_prompt": prompt},
        ),
    )


def main() -> int:
    """Apply a reversible group behavior extension to one existing persona."""
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("apply", "restore"))
    parser.add_argument("--persona-id", default="concise_group")
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(__file__).parents[1] / "runtime" / "group-behavior-backup.json",
    )
    args = parser.parse_args()
    base_url = os.environ.get(
        "ASTRBOT_DASHBOARD_URL", "http://127.0.0.1:6185/api/v1"
    ).rstrip("/")
    client = authenticated_client(base_url)
    try:
        if args.action == "apply":
            persona = get_persona(client, base_url, args.persona_id)
            original_prompt = str(persona.get("system_prompt", ""))
            updated_prompt = compose_group_persona_prompt(original_prompt)
            if updated_prompt == original_prompt:
                print(json.dumps({"status": "ok", "action": "apply", "changed": False}))
                return 0
            args.state_file.parent.mkdir(parents=True, exist_ok=True)
            args.state_file.write_text(
                json.dumps(
                    {"persona_id": args.persona_id, "system_prompt": original_prompt},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            update_prompt(client, base_url, args.persona_id, updated_prompt)
            print(json.dumps({"status": "ok", "action": "apply", "changed": True}))
        else:
            state = json.loads(args.state_file.read_text(encoding="utf-8"))
            persona_id = str(state["persona_id"])
            original_prompt = str(state["system_prompt"])
            update_prompt(client, base_url, persona_id, original_prompt)
            print(json.dumps({"status": "ok", "action": "restore", "changed": True}))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
